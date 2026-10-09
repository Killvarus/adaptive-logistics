from app.domain.models import PlanMetrics
from app.economics.costs import order_revenue
from app.planning.types import Assignment
from app.simulation.scenarios import ScenarioSnapshot


def build_metrics(snapshot: ScenarioSnapshot, assignment: Assignment, total_cost: int) -> tuple[PlanMetrics, int]:
    catalog = snapshot.catalog
    pct = snapshot.scenario.customer_rate_change_pct
    own_ids = [order_id for route in assignment.routes for order_id in route.order_ids]
    out_ids = [item.order_id for item in assignment.outsourced]
    unserved_ids = [item.order_id for item in assignment.unserved]
    recognized = sum(
        order_revenue(catalog.orders[order_id].base_revenue_kopecks, pct) for order_id in own_ids + out_ids
    )
    exposure = sum(
        order_revenue(catalog.orders[order_id].base_revenue_kopecks, pct) for order_id in unserved_ids
    )
    result = recognized - total_cost
    margin = None if recognized == 0 else (result / recognized) * 100
    total_orders = len(snapshot.active_orders)
    served = len(own_ids) + len(out_ids)
    service_rate = None if total_orders == 0 else served / total_orders

    own_distance = sum(route.schedule.distance_m for route in assignment.routes)
    loaded = sum(route.schedule.loaded_distance_m for route in assignment.routes)
    empty = sum(route.schedule.empty_distance_m for route in assignment.routes)
    loaded_share = None if own_distance == 0 else loaded / own_distance

    numerator = 0
    denominator = 0
    for route in assignment.routes:
        capacity = catalog.vehicles[route.vehicle_id].capacity_kg
        for leg in route.schedule.legs:
            numerator += leg.load_kg * leg.distance_m
            denominator += capacity * leg.distance_m
    utilization = None if denominator == 0 else numerator / denominator

    slacks = [route.schedule.maintenance_slack_m for route in assignment.routes]
    min_maintenance = min(slacks) if slacks else None

    delivery_slacks = [
        slack for route in assignment.routes for slack in route.schedule.delivery_slack_min.values()
    ]
    for item in assignment.outsourced:
        order = catalog.orders[item.order_id]
        offer = catalog.offers[item.offer_id]
        delivery_slacks.append(order.delivery_deadline_min - offer.planned_delivery_complete_min)
    min_delivery = min(delivery_slacks) if delivery_slacks else None

    metrics = PlanMetrics(
        recognized_revenue_kopecks=recognized,
        total_cost_kopecks=total_cost,
        operating_result_kopecks=result,
        margin_pct=margin,
        total_orders=total_orders,
        served_orders=served,
        own_served_orders=len(own_ids),
        outsourced_orders=len(out_ids),
        unserved_orders=len(unserved_ids),
        service_rate=service_rate,
        own_distance_m=own_distance,
        own_loaded_distance_m=loaded,
        own_empty_distance_m=empty,
        own_loaded_distance_share=loaded_share,
        capacity_utilization=utilization,
        min_maintenance_slack_m=min_maintenance,
        min_delivery_slack_min=min_delivery,
    )
    return metrics, exposure
