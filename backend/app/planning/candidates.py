from dataclasses import dataclass
from itertools import permutations

from app.config import MAX_CHAIN_LENGTH
from app.domain.models import Vehicle
from app.economics.costs import offer_price
from app.planning.baseline import _offer_fits, _simulate, build_own_route, usable_vehicles
from app.planning.types import Assignment, OwnRoute, PricedOffer
from app.simulation.scenarios import ScenarioSnapshot
from app.simulation.schedule import ScheduleFailure


@dataclass(frozen=True)
class ConstraintNote:
    vehicle_id: str
    message: str


def generate_candidates(
    snapshot: ScenarioSnapshot,
    baseline: Assignment,
) -> tuple[list[OwnRoute], list[ConstraintNote]]:
    candidates: dict[tuple[str, str, tuple[str, ...]], OwnRoute] = {}
    notes: list[ConstraintNote] = []
    order_map = {order.id: order for order in snapshot.active_orders}
    active = sorted(snapshot.active_orders, key=lambda order: order.id)

    for vehicle, driver in usable_vehicles(snapshot):
        compatible = [
            order
            for order in active
            if vehicle.body_type == order.required_body_type and order.weight_kg <= vehicle.capacity_kg
        ]
        success = 0
        failed_distances: list[int] = []
        ids = [order.id for order in compatible]
        upper = min(MAX_CHAIN_LENGTH, len(ids))
        for length in range(1, upper + 1):
            policy = "return_between_orders" if length == 1 else "direct_chaining"
            for sequence in permutations(ids, length):
                orders = [order_map[order_id] for order_id in sequence]
                schedule = _simulate(snapshot, vehicle, driver, orders, policy)
                if isinstance(schedule, ScheduleFailure):
                    if schedule.code == "maintenance" and schedule.distance_m:
                        failed_distances.append(schedule.distance_m)
                    continue
                success += 1
                _store(
                    candidates,
                    build_own_route(vehicle, driver, policy, orders, schedule, snapshot),
                )
        if compatible and success == 0:
            notes.append(ConstraintNote(vehicle.id, _maintenance_message(snapshot, vehicle, failed_distances)))

    for route in baseline.routes:
        vehicle = snapshot.catalog.vehicles[route.vehicle_id]
        driver = snapshot.catalog.drivers[route.driver_id]
        orders = [order_map[order_id] for order_id in route.order_ids]
        schedule = _simulate(snapshot, vehicle, driver, orders, route.policy)
        if isinstance(schedule, ScheduleFailure):
            continue
        _store(candidates, build_own_route(vehicle, driver, route.policy, orders, schedule, snapshot))
    ordered = [candidates[key] for key in sorted(candidates)]
    return ordered, notes


def priced_offers(snapshot: ScenarioSnapshot) -> list[PricedOffer]:
    active = {order.id: order for order in snapshot.active_orders}
    result: list[PricedOffer] = []
    for offer in sorted(snapshot.catalog.offers.values(), key=lambda item: item.id):
        order = active.get(offer.order_id)
        if order is None or not _offer_fits(snapshot, offer, order):
            continue
        result.append(
            PricedOffer(
                offer_id=offer.id,
                carrier_id=offer.carrier_id,
                order_id=offer.order_id,
                price_kopecks=offer_price(offer, snapshot.scenario.carrier_rate_change_pct),
                planned_pickup_min=offer.planned_pickup_min,
                planned_delivery_complete_min=offer.planned_delivery_complete_min,
            )
        )
    return result


def _store(candidates: dict[tuple[str, str, tuple[str, ...]], OwnRoute], route: OwnRoute) -> None:
    key = (route.vehicle_id, route.policy, tuple(route.order_ids))
    current = candidates.get(key)
    if current is None or route.variable_cost_kopecks < current.variable_cost_kopecks:
        candidates[key] = route


def _maintenance_message(snapshot: ScenarioSnapshot, vehicle: Vehicle, failed_distances: list[int]) -> str:
    due = snapshot.maintenance_due_m(vehicle.id, vehicle.maintenance_due_in_m) - vehicle.maintenance_buffer_m
    if not failed_distances:
        return f"{vehicle.id} не получила маршрут: нет допустимой цепочки в пределах смены и ограничений."
    required_km = min(failed_distances) / 1000
    available_km = due / 1000
    return (
        f"{vehicle.id} не назначена: рейс с возвратом не укладывается в остаток до ТО. "
        f"Требуется не меньше {required_km:.0f} км с возвратом, доступно {available_km:.0f} км до ТО с учётом буфера."
    )

