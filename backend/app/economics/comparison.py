from app.domain.models import Plan, PlanComparison


def _served(plan: Plan) -> set[str]:
    own = {order_id for route in plan.routes for order_id in route.order_ids}
    outsourced = {item.order_id for item in plan.outsourced_assignments}
    return own | outsourced


def _active(plan: Plan) -> set[str]:
    return _served(plan) | {item.order_id for item in plan.unserved_orders}


def compare_plans(baseline: Plan, optimized: Plan) -> PlanComparison:
    same_served = _served(baseline) == _served(optimized)
    same_active = _active(baseline) == _active(optimized)
    comparable = same_active and same_served
    base = baseline.metrics
    alt = optimized.metrics
    cost_delta = alt.total_cost_kopecks - base.total_cost_kopecks
    saving = base.total_cost_kopecks - alt.total_cost_kopecks
    if comparable and base.total_cost_kopecks:
        saving_pct = (saving / base.total_cost_kopecks) * 100
    else:
        saving_pct = None
    if base.margin_pct is None or alt.margin_pct is None:
        margin_delta = None
    else:
        margin_delta = alt.margin_pct - base.margin_pct
    notes: list[str] = []
    if not comparable:
        notes.append(
            "Изменились объём выполнения и выручка. "
            "Ниже — финансовая разница, а не сопоставимая экономия на том же сервисе."
        )
    elif saving == 0:
        notes.append("Среди проверенных вариантов затраты не снизились.")
    return PlanComparison(
        same_active_orders=same_active,
        same_served_orders=same_served,
        comparable_cost_saving=comparable,
        cost_delta_kopecks=cost_delta,
        cost_saving_kopecks=saving,
        cost_saving_pct=saving_pct,
        revenue_delta_kopecks=alt.recognized_revenue_kopecks - base.recognized_revenue_kopecks,
        operating_result_delta_kopecks=alt.operating_result_kopecks - base.operating_result_kopecks,
        margin_delta_pp=margin_delta,
        empty_distance_delta_m=alt.own_empty_distance_m - base.own_empty_distance_m,
        notes=notes,
    )
