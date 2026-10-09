from collections import Counter

from app.domain.models import Plan, ValidationCheck, ValidationReport
from app.economics.costs import offer_price
from app.economics.ledger import compute_plan
from app.planning.baseline import _offer_fits, build_own_route
from app.planning.types import Assignment, OutAssignment, Unserved
from app.simulation.scenarios import ScenarioSnapshot
from app.simulation.schedule import ScheduleFailure, simulate_route


def validate_plan(plan: Plan, snapshot: ScenarioSnapshot) -> ValidationReport:
    checks: list[ValidationCheck] = []

    def add(ok: bool, check_id: str, message: str, entity_ids: list[str] | None = None) -> None:
        checks.append(
            ValidationCheck(
                id=check_id,
                status="pass" if ok else "fail",
                message=message,
                entity_ids=entity_ids or [],
            )
        )

    active = {order.id for order in snapshot.active_orders}
    own = [order_id for route in plan.routes for order_id in route.order_ids]
    outsourced = [item.order_id for item in plan.outsourced_assignments]
    unserved = [item.order_id for item in plan.unserved_orders]
    combined = own + outsourced + unserved
    add(
        len(combined) == len(set(combined)) and set(combined) == active,
        "orders_once",
        "Каждый активный заказ учтён ровно один раз.",
        combined,
    )
    vehicle_ids = [route.vehicle_id for route in plan.routes]
    driver_ids = [route.driver_id for route in plan.routes]
    add(len(vehicle_ids) == len(set(vehicle_ids)), "vehicle_once", "У машины не больше одного маршрута за смену.")
    add(len(driver_ids) == len(set(driver_ids)), "driver_once", "Водитель не назначен на две машины.")

    loads = Counter(item.carrier_id for item in plan.outsourced_assignments)
    carrier_ok = all(
        count <= snapshot.catalog.carriers[carrier_id].max_orders_per_horizon for carrier_id, count in loads.items()
    )
    add(carrier_ok, "carrier_capacity", "Мощность подрядчика не превышена.")

    rebuilt_routes = []
    simulation_ok = True
    for route in plan.routes:
        vehicle = snapshot.catalog.vehicles[route.vehicle_id]
        driver = snapshot.catalog.drivers[route.driver_id]
        orders = [snapshot.catalog.orders[order_id] for order_id in route.order_ids]
        due = snapshot.maintenance_due_m(vehicle.id, vehicle.maintenance_due_in_m)
        schedule = simulate_route(
            snapshot.catalog.network,
            vehicle,
            driver,
            orders,
            policy=route.routing_policy,
            maintenance_due_m=due,
        )
        matches = (
            not isinstance(schedule, ScheduleFailure)
            and schedule.distance_m == route.distance_m
            and schedule.empty_distance_m == route.empty_distance_m
            and schedule.loaded_distance_m == route.loaded_distance_m
            and schedule.duty_min == route.duty_min
            and schedule.driving_min == route.driving_min
        )
        if not matches:
            simulation_ok = False
            continue
        rebuilt_routes.append(build_own_route(vehicle, driver, route.routing_policy, orders, schedule, snapshot))
    add(simulation_ok, "resimulate", "Повторная симуляция совпала с записанным маршрутом.")

    offer_ok = True
    rebuilt_offers: list[OutAssignment] = []
    for item in plan.outsourced_assignments:
        offer = snapshot.catalog.offers[item.offer_id]
        order = snapshot.catalog.orders[item.order_id]
        price = offer_price(offer, snapshot.scenario.carrier_rate_change_pct)
        if not _offer_fits(snapshot, offer, order) or price != item.price_kopecks:
            offer_ok = False
        rebuilt_offers.append(OutAssignment(offer_id=item.offer_id, carrier_id=item.carrier_id, order_id=item.order_id))
    add(offer_ok, "offers", "Внешние назначения повторно проходят проверку all-in тарифа.")

    if simulation_ok and offer_ok:
        assignment = Assignment(
            routes=rebuilt_routes,
            outsourced=rebuilt_offers,
            unserved=[
                Unserved(order_id=item.order_id, reason_code=item.reason_code, message=item.message)
                for item in plan.unserved_orders
            ],
        )
        rebuilt = compute_plan(
            plan_id=plan.id,
            kind=plan.kind,
            assignment=assignment,
            snapshot=snapshot,
            scenario_hash=plan.scenario_hash,
            baseline_mode=plan.baseline_mode,
            baseline_mode_reason=plan.baseline_mode_reason,
            validation=ValidationReport(ok=True, checks=[]),
        )
        money_ok = (
            rebuilt.ledger_totals_kopecks == plan.ledger_totals_kopecks
            and rebuilt.metrics.recognized_revenue_kopecks == plan.metrics.recognized_revenue_kopecks
            and rebuilt.metrics.operating_result_kopecks == plan.metrics.operating_result_kopecks
            and rebuilt.metrics.total_cost_kopecks == plan.metrics.total_cost_kopecks
        )
        add(money_ok, "ledger", "Повторный расчёт ledger совпал до копейки.")
    else:
        add(False, "ledger", "Ledger не подтверждён, потому что маршрут не сошёлся.")

    add(
        sum(plan.ledger_totals_kopecks.values()) == plan.metrics.total_cost_kopecks,
        "total_cost",
        "Сумма статей ledger равна total_cost.",
    )
    add(
        plan.metrics.operating_result_kopecks
        == plan.metrics.recognized_revenue_kopecks - plan.metrics.total_cost_kopecks,
        "operating_result",
        "Операционный результат равен выручке минус затраты.",
    )
    exposure_not_double = plan.metrics.operating_result_kopecks == (
        plan.metrics.recognized_revenue_kopecks - plan.metrics.total_cost_kopecks
    )
    add(exposure_not_double, "no_double_revenue", "Недополученная выручка не вычтена второй раз.")
    return ValidationReport(ok=all(check.status == "pass" for check in checks), checks=checks)
