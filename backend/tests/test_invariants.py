from copy import deepcopy
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.data.catalog import Catalog
from app.domain.models import Carrier, Dataset, Driver, Edge, Offer, Scenario, ScenarioInput
from app.domain.money import round_half_up
from app.domain.validation import validate_dataset
from app.errors import ApiError
from app.main import create_app
from app.planning.orchestrator import evaluate, optimize
from app.simulation.graph import RoadNetwork
from app.simulation.scenarios import build_snapshot, requested_count, select_active_orders
from app.simulation.schedule import ScheduleFailure, simulate_route
from app.validation import validate_plan


def _input(dataset: Dataset, **overrides) -> ScenarioInput:
    values = {
        "fuel_change_pct": 0,
        "wage_change_pct": 0,
        "carrier_rate_change_pct": 0,
        "customer_rate_change_pct": 0,
        "demand_change_pct": 0,
        "disabled_vehicle_ids": [],
        "disabled_driver_ids": [],
        "maintenance_remaining_overrides_m": {},
    }
    values.update(overrides)
    return ScenarioInput(
        dataset_id=dataset.metadata.dataset_id,
        dataset_version=dataset.metadata.dataset_version,
        scenario=Scenario(**values),
    )


def _catalog(dataset: Dataset) -> Catalog:
    errors = validate_dataset(dataset)
    assert errors == []
    return Catalog.from_dataset(dataset, "test-hash")


def test_rounding_half_up():
    assert round_half_up(Decimal("0.5")) == 1
    assert round_half_up(Decimal("1.5")) == 2
    assert round_half_up(Decimal("2.5")) == 3
    assert round_half_up(Decimal("2.4")) == 2


def test_demand_rounding():
    assert requested_count(18, -20) == 14
    assert requested_count(18, 30) == 23
    assert requested_count(2, 0) == 2
    assert requested_count(1, -50) == 1


def _edge(edge_id: str, source: str, target: str, distance_m: int, travel_time_min: int) -> Edge:
    return Edge(
        id=edge_id,
        from_node_id=source,
        to_node_id=target,
        distance_m=distance_m,
        travel_time_min=travel_time_min,
        max_payload_kg=None,
        allowed_body_types=[],
        provenance_id="p",
    )


def test_graph_uses_one_path_and_does_not_invent_reverse():
    edges = [
        _edge("short", "A", "B", 10, 50),
        _edge("long_a", "A", "C", 8, 1),
        _edge("long_b", "C", "B", 8, 1),
    ]
    network = RoadNetwork(edges)
    path = network.shortest_path("A", "B", load_kg=0, body_type="tent")
    assert path is not None
    assert path.distance_m == 10
    assert path.travel_time_min == 50
    assert path.edge_ids == ("short",)
    assert network.shortest_path("B", "A", load_kg=0, body_type="tent") is None


def test_graph_tie_break_by_edge_ids():
    edges = [
        _edge("b", "A", "B", 10, 9),
        _edge("a", "A", "C", 5, 1),
        _edge("c", "C", "B", 5, 1),
    ]
    path = RoadNetwork(edges).shortest_path("A", "B", load_kg=0, body_type="tent")
    assert path is not None
    assert path.distance_m == 10
    assert path.edge_ids == ("a", "c")
    assert path.travel_time_min == 2


def test_two_heavy_orders_fit_sequentially_but_not_one_overload(tiny_catalog):
    dataset = tiny_catalog.dataset
    vehicle = dataset.vehicles[0]
    driver = dataset.drivers[0]
    heavy = [
        dataset.order_pool[0].model_copy(update={"weight_kg": 8000}),
        dataset.order_pool[1].model_copy(update={"weight_kg": 8000}),
    ]
    schedule = simulate_route(
        tiny_catalog.network,
        vehicle,
        driver,
        heavy,
        policy="direct_chaining",
        maintenance_due_m=vehicle.maintenance_due_in_m,
    )
    assert not isinstance(schedule, ScheduleFailure)
    assert max(leg.load_kg for leg in schedule.legs) == 8000
    overload = simulate_route(
        tiny_catalog.network,
        vehicle,
        driver,
        [dataset.order_pool[0].model_copy(update={"weight_kg": 11000})],
        policy="return_between_orders",
        maintenance_due_m=vehicle.maintenance_due_in_m,
    )
    assert isinstance(overload, ScheduleFailure)
    assert overload.code == "capacity"


def test_maintenance_includes_return(tiny_catalog):
    dataset = tiny_catalog.dataset
    vehicle = dataset.vehicles[0]
    driver = dataset.drivers[0]
    blocked = simulate_route(
        tiny_catalog.network,
        vehicle,
        driver,
        [dataset.order_pool[0]],
        policy="return_between_orders",
        maintenance_due_m=150_000,
    )
    assert isinstance(blocked, ScheduleFailure)
    assert blocked.code == "maintenance"
    allowed = simulate_route(
        tiny_catalog.network,
        vehicle,
        driver,
        [dataset.order_pool[0]],
        policy="return_between_orders",
        maintenance_due_m=250_000,
    )
    assert not isinstance(allowed, ScheduleFailure)
    assert allowed.distance_m == 200_000
    assert allowed.maintenance_slack_m == 50_000


def test_fuel_change_touches_only_fuel_and_keeps_routes(tiny_catalog):
    result = evaluate(tiny_catalog, _input(tiny_catalog.dataset, fuel_change_pct=25))
    original = result.original.ledger_totals_kopecks
    baseline = result.baseline.ledger_totals_kopecks
    assert baseline["own_fuel"] == 1_000_000
    assert original["own_fuel"] == 800_000
    for key in original:
        if key != "own_fuel":
            assert baseline[key] == original[key]
    assert result.baseline.baseline_mode == "reprice_existing"
    assert result.original.metrics.own_distance_m == result.baseline.metrics.own_distance_m
    assert result.original.routes[0].order_ids == result.baseline.routes[0].order_ids


def test_wage_is_indexed_once_and_survives_idle_vehicle(tiny_catalog):
    result = evaluate(tiny_catalog, _input(tiny_catalog.dataset, wage_change_pct=10))
    assert result.baseline.ledger_totals_kopecks["driver_fixed_wage"] == 660_000
    assert result.original.ledger_totals_kopecks["driver_fixed_wage"] == 600_000
    assert result.baseline.ledger_totals_kopecks["own_fuel"] == result.original.ledger_totals_kopecks["own_fuel"]
    idle = evaluate(tiny_catalog, _input(tiny_catalog.dataset, disabled_vehicle_ids=["V-01"]))
    assert idle.baseline.baseline_mode == "replay_policy"
    assert "исходная политика применена повторно" in (idle.baseline.baseline_mode_reason or "")
    assert idle.baseline.routes == []
    assert idle.baseline.ledger_totals_kopecks["driver_fixed_wage"] == 600_000
    assert idle.baseline.ledger_totals_kopecks["fleet_fixed_cost"] == 200_000
    assert idle.baseline.metrics.margin_pct is None
    assert idle.baseline.unserved_revenue_exposure_kopecks == 2_100_000
    assert idle.baseline.metrics.operating_result_kopecks == (
        idle.baseline.metrics.recognized_revenue_kopecks - idle.baseline.metrics.total_cost_kopecks
    )
    assert idle.baseline.metrics.recognized_revenue_kopecks == 0


def test_outsourcing_is_all_in(tiny_catalog):
    dataset = tiny_catalog.dataset
    order = dataset.order_pool[0].model_copy(update={"outsourcing_allowed": True})
    carrier = Carrier(id="C-01", name="Подрядчик", max_orders_per_horizon=1, provenance_id="synthetic_reference")
    offer = Offer(
        id="Q-01",
        carrier_id="C-01",
        order_id="O-01",
        base_price_kopecks=100_000,
        planned_pickup_min=10,
        planned_delivery_complete_min=200,
        compatible=True,
        valid_for_planning_start=dataset.metadata.planning_start,
        provenance_id="synthetic_reference",
    )
    updated = dataset.model_copy(
        update={"order_pool": [order, dataset.order_pool[1]], "carriers": [carrier], "offers": [offer]}
    )
    catalog = _catalog(updated)
    result = evaluate(
        catalog,
        _input(updated, fuel_change_pct=25, carrier_rate_change_pct=10, disabled_vehicle_ids=["V-01"]),
    )
    totals = result.baseline.ledger_totals_kopecks
    assert totals["outsourcing"] == 110_000
    assert totals["own_fuel"] == 0
    assert totals["fleet_fixed_cost"] == 200_000
    assert totals["driver_fixed_wage"] == 600_000


def test_second_vehicle_keeps_fixed_cost(tiny_catalog):
    dataset = tiny_catalog.dataset
    extra_driver = Driver(
        id="D-02",
        available=True,
        available_from_min=0,
        available_until_min=600,
        max_driving_min=540,
        max_duty_min=600,
        fixed_wage_per_horizon_kopecks=100_000,
        variable_pay_per_hour_kopecks=0,
        provenance_id="synthetic_reference",
    )
    extra_vehicle = dataset.vehicles[0].model_copy(
        update={
            "id": "V-02",
            "assigned_driver_id": "D-02",
            "fixed_cost_per_horizon_kopecks": 50_000,
            "fuel_loaded_ml_per_km": 400,
        }
    )
    updated = dataset.model_copy(
        update={"drivers": [dataset.drivers[0], extra_driver], "vehicles": [dataset.vehicles[0], extra_vehicle]}
    )
    result = evaluate(_catalog(updated), _input(updated))
    assert result.original.ledger_totals_kopecks["fleet_fixed_cost"] == 250_000
    assert result.original.ledger_totals_kopecks["driver_fixed_wage"] == 700_000
    assert {route.vehicle_id for route in result.original.routes} == {"V-01"}


def test_pool_does_not_silently_clip_demand(tiny_catalog):
    with pytest.raises(ApiError) as caught:
        select_active_orders(tiny_catalog, 30)
    assert caught.value.status_code == 422


def test_validator_rejects_tampered_ledger(tiny_catalog):
    plan = evaluate(tiny_catalog, _input(tiny_catalog.dataset)).original
    tampered_entries = []
    for entry in plan.ledger:
        if entry.category == "own_fuel":
            tampered_entries.append(entry.model_copy(update={"amount_kopecks": entry.amount_kopecks + 1}))
        else:
            tampered_entries.append(entry)
    totals = dict(plan.ledger_totals_kopecks)
    totals["own_fuel"] += 1
    tampered = plan.model_copy(update={"ledger": tampered_entries, "ledger_totals_kopecks": totals})
    report = validate_plan(tampered, build_snapshot(tiny_catalog, _input(tiny_catalog.dataset)))
    assert report.ok is False


def test_infeasible_driver_has_no_fake_saving(tiny_catalog):
    result = optimize(tiny_catalog, _input(tiny_catalog.dataset, disabled_driver_ids=["D-01"]))
    assert result.business_status == "infeasible"
    assert result.optimized is None
    assert result.comparison is None
    assert result.baseline.service_status == "partial"


def test_single_order_has_zero_adaptation_effect(tiny_catalog):
    dataset = tiny_catalog.dataset.model_copy(
        update={"base_active_count": 1, "order_pool": [tiny_catalog.dataset.order_pool[0]]}
    )
    result = optimize(_catalog(dataset), _input(dataset, fuel_change_pct=25, wage_change_pct=10))
    assert result.business_status == "complete"
    assert result.optimized is not None
    assert result.comparison is not None
    assert result.comparison.comparable_cost_saving is True
    assert result.comparison.cost_saving_kopecks == 0
    assert result.comparison.cost_saving_pct == 0
    assert result.solver.solution_quality == "baseline_retained"


def test_api_contract(tiny_catalog):
    del tiny_catalog
    client = TestClient(create_app())
    health = client.get("/api/v1/health")
    assert health.status_code == 200
    body = health.json()
    assert body["status"] == "ok"
    assert body["demo_dataset_loaded"] is True
    assert body["solver_available"] is True
    payload = {
        "dataset_id": "tiny_backhaul",
        "dataset_version": "1.0.0",
        "scenario": {
            "fuel_change_pct": 25,
            "wage_change_pct": 10,
            "carrier_rate_change_pct": 0,
            "customer_rate_change_pct": 0,
            "demand_change_pct": 0,
            "disabled_vehicle_ids": [],
            "disabled_driver_ids": [],
            "maintenance_remaining_overrides_m": {},
        },
        "objective": "min_cost_with_full_service",
    }
    optimized = client.post("/api/v1/optimize", json=payload)
    assert optimized.status_code == 200
    data = optimized.json()
    assert data["optimized"]["metrics"]["total_cost_kopecks"] == 1_460_000
    assert "Traceback" not in optimized.text
    extra = deepcopy(payload)
    extra["scenario"]["labor_pct"] = 10
    rejected = client.post("/api/v1/evaluate", json=extra)
    assert rejected.status_code == 422
    assert "Traceback" not in rejected.text
    over = deepcopy(payload)
    over["scenario"]["fuel_change_pct"] = 80
    assert client.post("/api/v1/evaluate", json=over).status_code == 422
    missing = deepcopy(payload)
    missing["dataset_id"] = "../secret"
    assert client.post("/api/v1/evaluate", json=missing).status_code == 422
    unknown = deepcopy(payload)
    unknown["dataset_id"] = "no_such_dataset"
    assert client.post("/api/v1/evaluate", json=unknown).status_code == 404
    assert client.get("/api/v1/missing").status_code == 404
    demo = client.get("/api/v1/datasets/demo")
    assert demo.status_code == 200
    assert demo.json()["dataset"]["metadata"]["dataset_id"] == "demo_ru_regional_01"
    assert demo.json()["input_bounds"]["fuel_change_pct"]["max"] == 60
