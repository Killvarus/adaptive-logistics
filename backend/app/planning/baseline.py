from collections import Counter

from app.domain.models import Driver, Offer, Order, Vehicle
from app.economics.costs import offer_price, price_route
from app.planning.types import Assignment, OutAssignment, OwnRoute, Unserved
from app.simulation.scenarios import ScenarioSnapshot
from app.simulation.schedule import Schedule, ScheduleFailure, simulate_route


def block_reason(vehicle: Vehicle, driver: Driver, snapshot: ScenarioSnapshot) -> str | None:
    if vehicle.id in snapshot.disabled_vehicles or not vehicle.available:
        return "vehicle_unavailable"
    if driver.id in snapshot.disabled_drivers or not driver.available:
        return "driver_unavailable"
    return None


def usable_vehicles(snapshot: ScenarioSnapshot) -> list[tuple[Vehicle, Driver]]:
    pairs: list[tuple[Vehicle, Driver]] = []
    for vehicle in sorted(snapshot.catalog.vehicles.values(), key=lambda item: item.id):
        driver = snapshot.catalog.drivers[vehicle.assigned_driver_id]
        if block_reason(vehicle, driver, snapshot) is None:
            pairs.append((vehicle, driver))
    return pairs


def build_own_route(
    vehicle: Vehicle,
    driver: Driver,
    policy: str,
    orders: list[Order],
    schedule: Schedule,
    snapshot: ScenarioSnapshot,
) -> OwnRoute:
    cost = price_route(schedule, vehicle, driver, snapshot)
    return OwnRoute(
        vehicle_id=vehicle.id,
        driver_id=driver.id,
        policy=policy,  # type: ignore[arg-type]
        order_ids=[order.id for order in orders],
        schedule=schedule,
        fuel_kopecks=cost.fuel,
        wear_kopecks=cost.wear,
        variable_pay_kopecks=cost.variable_pay,
        activation_kopecks=cost.activation,
        variable_cost_kopecks=cost.variable_total,
    )


def run_baseline(
    snapshot: ScenarioSnapshot,
    *,
    locked_order_ids: set[str] | None = None,
    blocked_vehicle_ids: set[str] | None = None,
) -> Assignment:
    locked = locked_order_ids or set()
    blocked = blocked_vehicle_ids or set()
    pairs = [(vehicle, driver) for vehicle, driver in usable_vehicles(snapshot) if vehicle.id not in blocked]
    sequences: dict[str, list[str]] = {vehicle.id: [] for vehicle, _ in pairs}
    schedules: dict[str, Schedule] = {}
    order_map = {order.id: order for order in snapshot.active_orders}
    pending = [
        order
        for order in sorted(snapshot.active_orders, key=lambda item: (item.delivery_deadline_min, item.id))
        if order.id not in locked
    ]
    outsourced: list[OutAssignment] = []
    unserved: list[Unserved] = []
    carrier_load: Counter[str] = Counter()

    for order in pending:
        best: tuple[tuple[int, str], Vehicle, Driver, Schedule] | None = None
        failure_codes: list[str] = []
        for vehicle, driver in pairs:
            if not _fits_vehicle(vehicle, order):
                continue
            current_ids = sequences[vehicle.id]
            trial_orders = [order_map[order_id] for order_id in current_ids] + [order]
            schedule = _simulate(snapshot, vehicle, driver, trial_orders, "return_between_orders")
            if isinstance(schedule, ScheduleFailure):
                failure_codes.append(schedule.code)
                continue
            new_cost = price_route(schedule, vehicle, driver, snapshot).variable_total
            old_cost = 0
            if current_ids:
                old_cost = price_route(schedules[vehicle.id], vehicle, driver, snapshot).variable_total
            incremental = new_cost - old_cost
            key = (incremental, vehicle.id)
            if best is None or key < best[0]:
                best = (key, vehicle, driver, schedule)
        if best is not None:
            vehicle = best[1]
            sequences[vehicle.id].append(order.id)
            schedules[vehicle.id] = best[3]
            continue
        chosen = _cheapest_offer(snapshot, order, carrier_load)
        if chosen is not None:
            outsourced.append(
                OutAssignment(offer_id=chosen.id, carrier_id=chosen.carrier_id, order_id=order.id)
            )
            carrier_load[chosen.carrier_id] += 1
            continue
        unserved.append(_unserved(snapshot, order, failure_codes))

    routes: list[OwnRoute] = []
    for vehicle, driver in pairs:
        order_ids = sequences[vehicle.id]
        if not order_ids:
            continue
        schedule = schedules[vehicle.id]
        routes.append(
            build_own_route(
                vehicle,
                driver,
                "return_between_orders",
                [order_map[order_id] for order_id in order_ids],
                schedule,
                snapshot,
            )
        )
    return Assignment(routes=routes, outsourced=outsourced, unserved=unserved)


def reprice_assignment(assignment: Assignment, snapshot: ScenarioSnapshot) -> Assignment | None:
    order_map = {order.id: order for order in snapshot.active_orders}
    routes: list[OwnRoute] = []
    for route in assignment.routes:
        if any(order_id not in order_map for order_id in route.order_ids):
            return None
        vehicle = snapshot.catalog.vehicles[route.vehicle_id]
        driver = snapshot.catalog.drivers[route.driver_id]
        if block_reason(vehicle, driver, snapshot) is not None:
            return None
        orders = [order_map[order_id] for order_id in route.order_ids]
        schedule = _simulate(snapshot, vehicle, driver, orders, route.policy)
        if isinstance(schedule, ScheduleFailure):
            return None
        routes.append(build_own_route(vehicle, driver, route.policy, orders, schedule, snapshot))
    for item in assignment.outsourced:
        if item.order_id not in order_map:
            return None
        offer = snapshot.catalog.offers.get(item.offer_id)
        if offer is None or not _offer_fits(snapshot, offer, order_map[item.order_id]):
            return None
    return Assignment(routes=routes, outsourced=list(assignment.outsourced), unserved=list(assignment.unserved))


def _fits_vehicle(vehicle: Vehicle, order: Order) -> bool:
    return vehicle.body_type == order.required_body_type and order.weight_kg <= vehicle.capacity_kg


def _simulate(snapshot, vehicle, driver, orders, policy):
    due = snapshot.maintenance_due_m(vehicle.id, vehicle.maintenance_due_in_m)
    return simulate_route(
        snapshot.catalog.network,
        vehicle,
        driver,
        orders,
        policy=policy,
        maintenance_due_m=due,
    )


def _offer_fits(snapshot: ScenarioSnapshot, offer: Offer, order: Order) -> bool:
    if not offer.compatible or not order.outsourcing_allowed or offer.order_id != order.id:
        return False
    planning_start = snapshot.catalog.dataset.metadata.planning_start
    if offer.valid_for_planning_start not in (None, planning_start):
        return False
    if offer.planned_pickup_min < order.pickup_earliest_min or offer.planned_pickup_min > order.pickup_latest_min:
        return False
    return offer.planned_delivery_complete_min <= order.delivery_deadline_min


def _cheapest_offer(snapshot: ScenarioSnapshot, order: Order, carrier_load: Counter[str]) -> Offer | None:
    best: tuple[int, str, Offer] | None = None
    for offer in snapshot.catalog.offers.values():
        if not _offer_fits(snapshot, offer, order):
            continue
        carrier = snapshot.catalog.carriers[offer.carrier_id]
        if carrier_load[carrier.id] >= carrier.max_orders_per_horizon:
            continue
        price = offer_price(offer, snapshot.scenario.carrier_rate_change_pct)
        key = (price, offer.id)
        if best is None or key < (best[0], best[1]):
            best = (price, offer.id, offer)
    return None if best is None else best[2]


def _unserved(snapshot: ScenarioSnapshot, order: Order, failure_codes: list[str]) -> Unserved:
    physical = [
        vehicle
        for vehicle in snapshot.catalog.vehicles.values()
        if _fits_vehicle(vehicle, order)
    ]
    usable_ids = {vehicle.id for vehicle, _ in usable_vehicles(snapshot)}
    blocked_drivers = [
        vehicle
        for vehicle in physical
        if vehicle.id not in usable_ids
        and block_reason(vehicle, snapshot.catalog.drivers[vehicle.assigned_driver_id], snapshot)
        == "driver_unavailable"
    ]
    if not physical:
        return Unserved(
            order.id,
            "incompatible",
            "Нет доступной машины с подходящим кузовом и грузоподъёмностью. Подходящего предложения подрядчика нет.",
        )
    if blocked_drivers and not any(vehicle.id in usable_ids for vehicle in physical):
        driver_id = snapshot.catalog.drivers[blocked_drivers[0].assigned_driver_id].id
        return Unserved(
            order.id,
            "driver_unavailable",
            f"Машина исправна, но недоступна для плана: водитель {driver_id} отсутствует.",
        )
    if failure_codes and set(failure_codes) <= {"maintenance"}:
        return Unserved(
            order.id,
            "maintenance",
            "Собственный рейс не проходит по пробегу до ТО с учётом возврата. Подходящего предложения подрядчика нет.",
        )
    if any(code in {"shift", "duty", "driving", "pickup_window", "delivery_deadline"} for code in failure_codes):
        return Unserved(
            order.id,
            "time_window",
            "Собственный рейс не укладывается в смену или временное окно. Подходящего предложения подрядчика нет.",
        )
    if "unreachable" in failure_codes:
        return Unserved(
            order.id,
            "unreachable",
            "Нет допустимого пути между точками заказа. Подходящего предложения подрядчика нет.",
        )
    return Unserved(
        order.id,
        "no_option",
        "Нет допустимого собственного рейса и подходящего предложения подрядчика.",
    )
