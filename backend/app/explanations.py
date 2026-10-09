from app.domain.models import Plan, PlanChange
from app.planning.candidates import ConstraintNote


def explain(plan_b: Plan, plan_c: Plan | None, notes: list[ConstraintNote]) -> list[PlanChange]:
    if plan_c is None:
        return []
    changes: list[PlanChange] = []
    baseline_by_orders = {tuple(route.order_ids): route for route in plan_b.routes}
    for route in plan_c.routes:
        if route.routing_policy != "direct_chaining" or len(route.order_ids) < 2:
            continue
        previous = baseline_by_orders.get(tuple(route.order_ids))
        physical = None
        if previous is not None:
            reduction = previous.empty_distance_m - route.empty_distance_m
            if reduction > 0:
                physical = f"В этой цепочке пустой пробег уменьшился на {_km(reduction)} км."
        changes.append(
            PlanChange(
                id=f"chain-{route.id}",
                type="chain",
                title=f"{route.vehicle_id}: {' → '.join(route.order_ids)}",
                explanation=(
                    f"Заказы {', '.join(route.order_ids)} связаны в последовательную цепочку {route.vehicle_id}. "
                    "Между ними не требуется возврат на базу."
                ),
                order_ids=list(route.order_ids),
                vehicle_ids=[route.vehicle_id],
                route_ids=[route.id],
                physical_effect=physical,
                financial_effect_kopecks=None,
                financial_effect_scope="not_isolated",
            )
        )
    baseline_outsourced = {item.order_id for item in plan_b.outsourced_assignments}
    for item in plan_c.outsourced_assignments:
        if item.order_id in baseline_outsourced:
            continue
        changes.append(
            PlanChange(
                id=f"out-{item.order_id}",
                type="outsource",
                title=f"Подрядчик {item.carrier_id}: {item.order_id}",
                explanation=(
                    "Заказ передан подрядчику. Тариф all-in уже включает его топливо, машину и водителя; "
                    "расходы собственного парка на этот заказ не начисляются."
                ),
                order_ids=[item.order_id],
                vehicle_ids=[],
                route_ids=[],
                physical_effect=None,
                financial_effect_kopecks=None,
                financial_effect_scope="not_isolated",
            )
        )
    for note in notes:
        changes.append(
            PlanChange(
                id=f"limit-{note.vehicle_id}",
                type="constraint",
                title=note.vehicle_id,
                explanation=note.message,
                order_ids=[],
                vehicle_ids=[note.vehicle_id],
                route_ids=[],
                physical_effect=None,
                financial_effect_kopecks=None,
                financial_effect_scope=None,
            )
        )
    if changes:
        return changes
    return [
        PlanChange(
            id="unchanged",
            type="unchanged",
            title="Без изменений",
            explanation="Сохраняем исходный допустимый план. Среди проверенных вариантов более дешёвого нет.",
            order_ids=[],
            vehicle_ids=[],
            route_ids=[],
            physical_effect=None,
            financial_effect_kopecks=0,
            financial_effect_scope="plan",
        )
    ]


def _km(distance_m: int) -> str:
    if distance_m % 1000 == 0:
        return str(distance_m // 1000)
    text = f"{distance_m / 1000:.1f}"
    return text.replace(".", ",")
