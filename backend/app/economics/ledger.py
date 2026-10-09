from app.config import LEDGER_CATEGORIES
from app.domain.models import (
    LedgerEntry,
    OutsourcedAssignment,
    Plan,
    PlanKind,
    Route,
    ServiceStatus,
    UnservedOrder,
    ValidationReport,
)
from app.economics.costs import fixed_wage, offer_price, order_revenue
from app.economics.metrics import build_metrics
from app.planning.types import Assignment
from app.simulation.scenarios import ScenarioSnapshot


def compute_plan(
    *,
    plan_id: str,
    kind: PlanKind,
    assignment: Assignment,
    snapshot: ScenarioSnapshot,
    scenario_hash: str,
    baseline_mode,
    baseline_mode_reason: str | None,
    validation: ValidationReport,
) -> Plan:
    catalog = snapshot.catalog
    scenario = snapshot.scenario
    entries: list[LedgerEntry] = []
    totals = {category: 0 for category in LEDGER_CATEGORIES}

    def add(entry: LedgerEntry) -> None:
        entries.append(entry)
        totals[entry.category] += entry.amount_kopecks

    routes: list[Route] = []
    for own in sorted(assignment.routes, key=lambda item: (item.vehicle_id, item.order_ids)):
        tag = "D" if own.policy == "direct_chaining" else "R"
        route_id = f"{tag}-{own.vehicle_id}-{'-'.join(own.order_ids)}"
        schedule = own.schedule
        routes.append(
            Route(
                id=route_id,
                vehicle_id=own.vehicle_id,
                driver_id=own.driver_id,
                routing_policy=own.policy,
                order_ids=list(own.order_ids),
                events=list(schedule.events),
                legs=list(schedule.legs),
                start_min=schedule.start_min,
                finish_min=schedule.finish_min,
                duty_min=schedule.duty_min,
                driving_min=schedule.driving_min,
                distance_m=schedule.distance_m,
                empty_distance_m=schedule.empty_distance_m,
                loaded_distance_m=schedule.loaded_distance_m,
                variable_cost_kopecks=own.variable_cost_kopecks,
                maintenance_slack_m=schedule.maintenance_slack_m,
                delivery_slack_min=dict(schedule.delivery_slack_min),
            )
        )
        if own.fuel_kopecks:
            add(
                LedgerEntry(
                    category="own_fuel",
                    amount_kopecks=own.fuel_kopecks,
                    scope="route",
                    entity_id=route_id,
                    formula_note="Топливо маршрута: литры × цена, одно округление до копейки.",
                )
            )
        if own.wear_kopecks:
            add(
                LedgerEntry(
                    category="own_wear",
                    amount_kopecks=own.wear_kopecks,
                    scope="route",
                    entity_id=route_id,
                    formula_note="Пробег в км × условный тариф износа.",
                )
            )
        if own.variable_pay_kopecks:
            add(
                LedgerEntry(
                    category="driver_variable_pay",
                    amount_kopecks=own.variable_pay_kopecks,
                    scope="driver",
                    entity_id=own.driver_id,
                    formula_note="Время работы маршрута × переменная ставка с индексацией.",
                )
            )
        if own.activation_kopecks:
            add(
                LedgerEntry(
                    category="vehicle_activation",
                    amount_kopecks=own.activation_kopecks,
                    scope="route",
                    entity_id=own.vehicle_id,
                    formula_note="Условная стоимость выпуска, только если машина назначена.",
                )
            )

    for driver in sorted(catalog.drivers.values(), key=lambda item: item.id):
        amount = fixed_wage(driver, scenario.wage_change_pct)
        add(
            LedgerEntry(
                category="driver_fixed_wage",
                amount_kopecks=amount,
                scope="driver",
                entity_id=driver.id,
                formula_note="Фиксированная оплата за горизонт начисляется и без рейса.",
            )
        )
    for vehicle in sorted(catalog.vehicles.values(), key=lambda item: item.id):
        add(
            LedgerEntry(
                category="fleet_fixed_cost",
                amount_kopecks=vehicle.fixed_cost_per_horizon_kopecks,
                scope="fleet",
                entity_id=vehicle.id,
                formula_note="Затраты владения за смену не зависят от пробега.",
            )
        )

    outsourced: list[OutsourcedAssignment] = []
    for item in sorted(assignment.outsourced, key=lambda row: row.order_id):
        offer = catalog.offers[item.offer_id]
        price = offer_price(offer, scenario.carrier_rate_change_pct)
        outsourced.append(
            OutsourcedAssignment(
                offer_id=item.offer_id,
                carrier_id=item.carrier_id,
                order_id=item.order_id,
                price_kopecks=price,
                planned_pickup_min=offer.planned_pickup_min,
                planned_delivery_complete_min=offer.planned_delivery_complete_min,
            )
        )
        add(
            LedgerEntry(
                category="outsourcing",
                amount_kopecks=price,
                scope="offer",
                entity_id=item.offer_id,
                formula_note="Тариф подрядчика all-in, без топлива собственного парка.",
            )
        )

    unserved: list[UnservedOrder] = []
    for item in sorted(assignment.unserved, key=lambda row: row.order_id):
        order = catalog.orders[item.order_id]
        unserved.append(
            UnservedOrder(order_id=item.order_id, reason_code=item.reason_code, message=item.message)
        )
        if order.cancellation_compensation_kopecks:
            add(
                LedgerEntry(
                    category="cancellation_compensation",
                    amount_kopecks=order.cancellation_compensation_kopecks,
                    scope="order",
                    entity_id=order.id,
                    formula_note="Только заданная компенсация. Недополученная выручка сюда не входит.",
                )
            )

    total_cost = sum(totals.values())
    metrics, exposure = build_metrics(snapshot, assignment, total_cost)
    status: ServiceStatus = "complete" if not unserved else "partial"
    return Plan(
        id=plan_id,
        kind=kind,
        scenario_hash=scenario_hash,
        baseline_mode=baseline_mode,
        baseline_mode_reason=baseline_mode_reason,
        service_status=status,
        routes=routes,
        outsourced_assignments=outsourced,
        unserved_orders=unserved,
        ledger=entries,
        ledger_totals_kopecks=totals,
        unserved_revenue_exposure_kopecks=exposure,
        metrics=metrics,
        validation=validation,
    )


def recognized_revenue_for_check(snapshot: ScenarioSnapshot, order_ids: list[str]) -> int:
    pct = snapshot.scenario.customer_rate_change_pct
    return sum(order_revenue(snapshot.catalog.orders[order_id].base_revenue_kopecks, pct) for order_id in order_ids)
