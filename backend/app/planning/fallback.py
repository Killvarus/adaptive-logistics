import time
from itertools import permutations

from app.economics.costs import offer_price
from app.planning.baseline import build_own_route, run_baseline
from app.planning.types import Assignment, OwnRoute
from app.simulation.scenarios import ScenarioSnapshot
from app.simulation.schedule import ScheduleFailure, simulate_route


def fallback_search(
    snapshot: ScenarioSnapshot,
    baseline: Assignment,
    candidates: list[OwnRoute],
    *,
    time_limit_s: float,
) -> Assignment | None:
    """Локальный поиск от baseline. Оптимальность не доказывается."""
    started = time.perf_counter()
    best = _direct_variants(snapshot, baseline)
    best_key = _score(snapshot, best)
    order_map = {order.id: order for order in snapshot.active_orders}
    ranked = sorted(
        (route for route in candidates if len(route.order_ids) >= 2),
        key=lambda route: (
            route.variable_cost_kopecks / len(route.order_ids),
            route.variable_cost_kopecks,
            route.order_ids,
        ),
    )
    for route in ranked[:80]:
        if time.perf_counter() - started > time_limit_s:
            break
        covered = set(route.order_ids)
        rest = run_baseline(
            snapshot,
            locked_order_ids=covered,
            blocked_vehicle_ids={route.vehicle_id},
        )
        if _overlaps(route, rest):
            continue
        trial = Assignment(
            routes=[route, *rest.routes],
            outsourced=list(rest.outsourced),
            unserved=list(rest.unserved),
        )
        key = _score(snapshot, trial)
        if key < best_key:
            best = trial
            best_key = key
    if best_key[0] != 0:
        return None
    if best.routes and best.routes[0].order_ids and order_map:
        return best
    return best


def _direct_variants(snapshot: ScenarioSnapshot, baseline: Assignment) -> Assignment:
    routes = list(baseline.routes)
    order_map = {order.id: order for order in snapshot.active_orders}
    for index, route in enumerate(list(routes)):
        if len(route.order_ids) < 2 or len(route.order_ids) > 3:
            continue
        vehicle = snapshot.catalog.vehicles[route.vehicle_id]
        driver = snapshot.catalog.drivers[route.driver_id]
        best_route = route
        for sequence in permutations(route.order_ids):
            orders = [order_map[order_id] for order_id in sequence]
            due = snapshot.maintenance_due_m(vehicle.id, vehicle.maintenance_due_in_m)
            schedule = simulate_route(
                snapshot.catalog.network,
                vehicle,
                driver,
                orders,
                policy="direct_chaining",
                maintenance_due_m=due,
            )
            if isinstance(schedule, ScheduleFailure):
                continue
            candidate = build_own_route(vehicle, driver, "direct_chaining", orders, schedule, snapshot)
            if candidate.variable_cost_kopecks < best_route.variable_cost_kopecks:
                best_route = candidate
        routes[index] = best_route
    return Assignment(routes=routes, outsourced=list(baseline.outsourced), unserved=list(baseline.unserved))


def _score(snapshot: ScenarioSnapshot, assignment: Assignment) -> tuple[int, int]:
    complete = 0 if not assignment.unserved else 1
    variable = sum(route.variable_cost_kopecks for route in assignment.routes)
    external = 0
    for item in assignment.outsourced:
        offer = snapshot.catalog.offers[item.offer_id]
        external += offer_price(offer, snapshot.scenario.carrier_rate_change_pct)
    compensation = sum(
        snapshot.catalog.orders[item.order_id].cancellation_compensation_kopecks for item in assignment.unserved
    )
    return complete, variable + external + compensation


def _overlaps(route: OwnRoute, rest: Assignment) -> bool:
    covered = set(route.order_ids)
    for other in rest.routes:
        if other.vehicle_id == route.vehicle_id or covered.intersection(other.order_ids):
            return True
    for item in rest.outsourced:
        if item.order_id in covered:
            return True
    return False

