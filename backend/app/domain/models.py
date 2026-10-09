from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

LedgerCategory = Literal[
    "own_fuel",
    "own_wear",
    "driver_fixed_wage",
    "driver_variable_pay",
    "fleet_fixed_cost",
    "vehicle_activation",
    "outsourcing",
    "cancellation_compensation",
]
RoutingPolicy = Literal["direct_chaining", "return_between_orders"]
PlanKind = Literal["A", "B", "C"]
ServiceStatus = Literal["complete", "partial"]
BaselineMode = Literal["reprice_existing", "replay_policy"]
NodeKind = Literal["depot", "customer", "hub"]
LegKind = Literal["loaded", "empty"]
EventType = Literal["wait", "pickup", "delivery"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DatasetMetadata(StrictModel):
    schema_version: str
    dataset_id: str
    dataset_version: str
    dataset_kind: Literal["synthetic_demo", "company_provided"]
    seed: int
    planning_start: str
    timezone: str
    horizon_min: int = Field(gt=0)
    currency: Literal["RUB"]
    country_code: Literal["RU"]
    disclaimer: str


class Node(StrictModel):
    id: str
    name: str
    kind: NodeKind
    ui_x: float
    ui_y: float
    country_code: Literal["RU"]
    provenance_id: str


class Edge(StrictModel):
    id: str
    from_node_id: str
    to_node_id: str
    distance_m: int = Field(gt=0)
    travel_time_min: int = Field(gt=0)
    max_payload_kg: int | None = None
    allowed_body_types: list[str]
    provenance_id: str


class Order(StrictModel):
    id: str
    pickup_node_id: str
    delivery_node_id: str
    weight_kg: int = Field(gt=0)
    required_body_type: str
    sector_tag: str
    pickup_earliest_min: int = Field(ge=0)
    pickup_latest_min: int = Field(ge=0)
    delivery_deadline_min: int = Field(ge=0)
    pickup_service_min: int = Field(ge=0)
    delivery_service_min: int = Field(ge=0)
    base_revenue_kopecks: int = Field(ge=0)
    cancellation_compensation_kopecks: int = Field(ge=0)
    outsourcing_allowed: bool
    demand_rank: int
    provenance_id: str


class Vehicle(StrictModel):
    id: str
    name: str
    body_type: str
    capacity_kg: int = Field(gt=0)
    home_node_id: str
    assigned_driver_id: str
    available_from_min: int = Field(ge=0)
    available_until_min: int = Field(ge=0)
    available: bool
    maintenance_due_in_m: int = Field(ge=0)
    maintenance_buffer_m: int = Field(ge=0)
    fixed_cost_per_horizon_kopecks: int = Field(ge=0)
    activation_cost_kopecks: int = Field(ge=0)
    wear_kopecks_per_km: int = Field(ge=0)
    fuel_empty_ml_per_km: int = Field(gt=0)
    fuel_loaded_ml_per_km: int = Field(gt=0)
    provenance_id: str


class Driver(StrictModel):
    id: str
    available: bool
    available_from_min: int = Field(ge=0)
    available_until_min: int = Field(ge=0)
    max_driving_min: int = Field(ge=0)
    max_duty_min: int = Field(ge=0)
    fixed_wage_per_horizon_kopecks: int = Field(ge=0)
    variable_pay_per_hour_kopecks: int = Field(ge=0)
    provenance_id: str


class Carrier(StrictModel):
    id: str
    name: str
    max_orders_per_horizon: int = Field(ge=0)
    provenance_id: str


class Offer(StrictModel):
    id: str
    carrier_id: str
    order_id: str
    base_price_kopecks: int = Field(ge=0)
    planned_pickup_min: int = Field(ge=0)
    planned_delivery_complete_min: int = Field(ge=0)
    compatible: bool
    valid_for_planning_start: str | None
    provenance_id: str


class ProvenanceCard(StrictModel):
    id: str
    title: str
    kind: str
    source_url: str | None = None
    country_code: str | None = None
    note: str | None = None


class BaseParameters(StrictModel):
    fuel_price_kopecks_per_liter: int = Field(gt=0)


class Dataset(StrictModel):
    metadata: DatasetMetadata
    base_active_count: int = Field(ge=0)
    base_parameters: BaseParameters
    nodes: list[Node]
    edges: list[Edge]
    order_pool: list[Order]
    vehicles: list[Vehicle]
    drivers: list[Driver]
    carriers: list[Carrier]
    offers: list[Offer]
    provenance: list[ProvenanceCard]


class Scenario(StrictModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    fuel_change_pct: int
    wage_change_pct: int
    carrier_rate_change_pct: int
    customer_rate_change_pct: int
    demand_change_pct: int
    disabled_vehicle_ids: list[str]
    disabled_driver_ids: list[str]
    maintenance_remaining_overrides_m: dict[str, int]


class ScenarioInput(StrictModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    dataset_id: str
    dataset_version: str
    scenario: Scenario
    objective: Literal["min_cost_with_full_service"] = "min_cost_with_full_service"


class Leg(StrictModel):
    from_node_id: str
    to_node_id: str
    path_edge_ids: list[str]
    depart_min: int
    arrive_min: int
    distance_m: int
    load_kg: int
    order_id: str | None
    kind: LegKind


class RouteEvent(StrictModel):
    type: EventType
    node_id: str
    start_min: int
    finish_min: int
    order_id: str
    load_before_kg: int
    load_after_kg: int


class LedgerEntry(StrictModel):
    category: LedgerCategory
    amount_kopecks: int
    scope: Literal["fleet", "driver", "route", "offer", "order"]
    entity_id: str | None
    formula_note: str


class PlanMetrics(StrictModel):
    recognized_revenue_kopecks: int
    total_cost_kopecks: int
    operating_result_kopecks: int
    margin_pct: float | None
    total_orders: int
    served_orders: int
    own_served_orders: int
    outsourced_orders: int
    unserved_orders: int
    service_rate: float | None
    own_distance_m: int
    own_loaded_distance_m: int
    own_empty_distance_m: int
    own_loaded_distance_share: float | None
    capacity_utilization: float | None
    min_maintenance_slack_m: int | None
    min_delivery_slack_min: int | None


class ValidationCheck(StrictModel):
    id: str
    status: Literal["pass", "fail"]
    message: str
    entity_ids: list[str] = []


class ValidationReport(StrictModel):
    ok: bool
    checks: list[ValidationCheck]


class Route(StrictModel):
    id: str
    vehicle_id: str
    driver_id: str
    routing_policy: RoutingPolicy
    order_ids: list[str]
    events: list[RouteEvent]
    legs: list[Leg]
    start_min: int
    finish_min: int
    duty_min: int
    driving_min: int
    distance_m: int
    empty_distance_m: int
    loaded_distance_m: int
    variable_cost_kopecks: int
    maintenance_slack_m: int
    delivery_slack_min: dict[str, int]


class OutsourcedAssignment(StrictModel):
    offer_id: str
    carrier_id: str
    order_id: str
    price_kopecks: int
    planned_pickup_min: int
    planned_delivery_complete_min: int


class UnservedOrder(StrictModel):
    order_id: str
    reason_code: str
    message: str


class Plan(StrictModel):
    id: str
    kind: PlanKind
    scenario_hash: str
    baseline_mode: BaselineMode | None
    baseline_mode_reason: str | None
    service_status: ServiceStatus
    routes: list[Route]
    outsourced_assignments: list[OutsourcedAssignment]
    unserved_orders: list[UnservedOrder]
    ledger: list[LedgerEntry]
    ledger_totals_kopecks: dict[str, int]
    unserved_revenue_exposure_kopecks: int
    metrics: PlanMetrics
    validation: ValidationReport


class EffectiveParameters(StrictModel):
    fuel_price_kopecks_per_liter: int
    fuel_change_pct: int
    wage_change_pct: int
    carrier_rate_change_pct: int
    customer_rate_change_pct: int
    demand_change_pct: int
    active_order_count: int
    base_active_order_count: int
    disabled_vehicle_ids: list[str]
    disabled_driver_ids: list[str]
    maintenance_remaining_overrides_m: dict[str, int]


class MarketImpact(StrictModel):
    operating_result_delta_kopecks: int
    cost_delta_kopecks: int
    revenue_delta_kopecks: int
    active_orders_changed: bool
    resources_changed: bool
    baseline_mode: BaselineMode
    notes: list[str]


class WarningItem(StrictModel):
    code: str
    message: str


class ProvenanceSummary(StrictModel):
    dataset_kind: str
    disclaimer: str
    cards: list[ProvenanceCard]


class ComputationMetadata(StrictModel):
    engine_version: str
    elapsed_ms: int
    dataset_id: str
    dataset_version: str
    dataset_hash: str


class PlanComparison(StrictModel):
    same_active_orders: bool
    same_served_orders: bool
    comparable_cost_saving: bool
    cost_delta_kopecks: int
    cost_saving_kopecks: int
    cost_saving_pct: float | None
    revenue_delta_kopecks: int
    operating_result_delta_kopecks: int
    margin_delta_pp: float | None
    empty_distance_delta_m: int
    notes: list[str]


class PlanChange(StrictModel):
    id: str
    type: Literal["chain", "outsource", "constraint", "unchanged"]
    title: str
    explanation: str
    order_ids: list[str]
    vehicle_ids: list[str]
    route_ids: list[str]
    physical_effect: str | None
    financial_effect_kopecks: int | None
    financial_effect_scope: str | None


class Diagnostic(StrictModel):
    code: str
    message: str
    order_ids: list[str] = []
    vehicle_ids: list[str] = []


class SolverInfo(StrictModel):
    engine: Literal["cp_sat_candidates", "fallback_local_search"]
    solver_status: str
    solution_quality: Literal[
        "optimal_within_candidates",
        "feasible",
        "heuristic",
        "baseline_retained",
        "none",
    ]
    candidate_count: int
    generated_max_chain_length: int
    elapsed_ms: int
    best_bound_kopecks: int | None
    note: str | None = None


class EvaluationResponse(StrictModel):
    schema_version: Literal["1.0"]
    run_id: str
    scenario_hash: str
    dataset_hash: str
    input: ScenarioInput
    effective_parameters: EffectiveParameters
    active_order_ids: list[str]
    original: Plan
    baseline: Plan
    market_impact: MarketImpact
    warnings: list[WarningItem]
    provenance: ProvenanceSummary
    computation: ComputationMetadata


class OptimizationResponse(EvaluationResponse):
    business_status: Literal["complete", "infeasible", "unresolved", "error"]
    optimized: Plan | None
    comparison: PlanComparison | None
    changes: list[PlanChange]
    diagnostics: list[Diagnostic]
    solver: SolverInfo
