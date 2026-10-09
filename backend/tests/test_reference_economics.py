import pytest

from app.domain.models import Scenario, ScenarioInput
from app.planning.orchestrator import optimize


def test_reference_economics(tiny_catalog, expected):
    scenario = ScenarioInput(
        dataset_id=tiny_catalog.dataset.metadata.dataset_id,
        dataset_version=tiny_catalog.dataset.metadata.dataset_version,
        scenario=Scenario(
            fuel_change_pct=25,
            wage_change_pct=10,
            carrier_rate_change_pct=0,
            customer_rate_change_pct=0,
            demand_change_pct=0,
            disabled_vehicle_ids=[],
            disabled_driver_ids=[],
            maintenance_remaining_overrides_m={},
        ),
    )
    result = optimize(tiny_catalog, scenario)
    assert result.business_status == "complete"
    assert result.optimized is not None
    assert result.comparison is not None
    _assert_state(result.original, expected["A"])
    _assert_state(result.baseline, expected["B"])
    _assert_state(result.optimized, expected["C"])
    comparison = result.comparison
    expected_comparison = expected["comparison_C_vs_B"]
    assert comparison.same_active_orders is True
    assert comparison.same_served_orders is True
    assert comparison.comparable_cost_saving is True
    assert comparison.cost_delta_kopecks == expected_comparison["cost_delta_kopecks"]
    assert comparison.cost_saving_kopecks == expected_comparison["cost_saving_kopecks"]
    assert comparison.cost_saving_pct == pytest.approx(expected_comparison["cost_saving_pct"])
    assert comparison.revenue_delta_kopecks == 0
    assert comparison.operating_result_delta_kopecks == expected_comparison["operating_result_delta_kopecks"]
    assert comparison.margin_delta_pp == pytest.approx(expected_comparison["margin_delta_pp"])
    assert comparison.empty_distance_delta_m == expected_comparison["empty_distance_delta_m"]
    wage_b = result.baseline.ledger_totals_kopecks["driver_fixed_wage"]
    wage_c = result.optimized.ledger_totals_kopecks["driver_fixed_wage"]
    fleet_b = result.baseline.ledger_totals_kopecks["fleet_fixed_cost"]
    fleet_c = result.optimized.ledger_totals_kopecks["fleet_fixed_cost"]
    assert wage_b == wage_c
    assert fleet_b == fleet_c
    assert result.original.routes[0].routing_policy == "return_between_orders"
    assert result.optimized.routes[0].routing_policy == "direct_chaining"
    assert [leg.kind for leg in result.original.routes[0].legs] == ["loaded", "empty", "empty", "loaded"]
    assert [leg.kind for leg in result.optimized.routes[0].legs] == ["loaded", "loaded"]


def _assert_state(plan, expected_state):
    assert plan.ledger_totals_kopecks == expected_state["ledger_categories_kopecks"]
    assert sum(entry.amount_kopecks for entry in plan.ledger) == plan.metrics.total_cost_kopecks
    metrics = plan.metrics
    for key, value in expected_state["metrics"].items():
        actual = getattr(metrics, key)
        if isinstance(value, float):
            assert actual == pytest.approx(value)
        else:
            assert actual == value
    assert plan.routes[0].duty_min == expected_state["route_duty_min"]
    assert plan.routes[0].driving_min == expected_state["route_driving_min"]
    assert plan.routes[0].order_ids == expected_state["route_order_ids"]
    assert plan.routes[0].routing_policy == expected_state["routing_policy"]
    assert plan.validation.ok is True
