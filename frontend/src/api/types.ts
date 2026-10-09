export type PlanKind = "A" | "B" | "C";
export type View = "overview" | "plan" | "data";

export interface Scenario {
  fuel_change_pct: number;
  wage_change_pct: number;
  carrier_rate_change_pct: number;
  customer_rate_change_pct: number;
  demand_change_pct: number;
  disabled_vehicle_ids: string[];
  disabled_driver_ids: string[];
  maintenance_remaining_overrides_m: Record<string, number>;
}

export interface ScenarioInput {
  dataset_id: string;
  dataset_version: string;
  scenario: Scenario;
  objective: "min_cost_with_full_service";
}

export interface PlanMetrics {
  recognized_revenue_kopecks: number;
  total_cost_kopecks: number;
  operating_result_kopecks: number;
  margin_pct: number | null;
  total_orders: number;
  served_orders: number;
  own_served_orders: number;
  outsourced_orders: number;
  unserved_orders: number;
  service_rate: number | null;
  own_distance_m: number;
  own_loaded_distance_m: number;
  own_empty_distance_m: number;
  own_loaded_distance_share: number | null;
  capacity_utilization: number | null;
  min_maintenance_slack_m: number | null;
  min_delivery_slack_min: number | null;
}

export interface Leg {
  from_node_id: string;
  to_node_id: string;
  path_edge_ids: string[];
  depart_min: number;
  arrive_min: number;
  distance_m: number;
  load_kg: number;
  order_id: string | null;
  kind: "loaded" | "empty";
}

export interface RouteEvent {
  type: "wait" | "pickup" | "delivery";
  node_id: string;
  start_min: number;
  finish_min: number;
  order_id: string;
  load_before_kg: number;
  load_after_kg: number;
}

export interface Route {
  id: string;
  vehicle_id: string;
  driver_id: string;
  routing_policy: "direct_chaining" | "return_between_orders";
  order_ids: string[];
  events: RouteEvent[];
  legs: Leg[];
  start_min: number;
  finish_min: number;
  duty_min: number;
  driving_min: number;
  distance_m: number;
  empty_distance_m: number;
  loaded_distance_m: number;
  variable_cost_kopecks: number;
  maintenance_slack_m: number;
  delivery_slack_min: Record<string, number>;
}

export interface LedgerEntry {
  category: string;
  amount_kopecks: number;
  scope: string;
  entity_id: string | null;
  formula_note: string;
}

export interface Plan {
  id: string;
  kind: PlanKind;
  scenario_hash: string;
  baseline_mode: "reprice_existing" | "replay_policy" | null;
  baseline_mode_reason: string | null;
  service_status: "complete" | "partial";
  routes: Route[];
  outsourced_assignments: Array<{
    offer_id: string;
    carrier_id: string;
    order_id: string;
    price_kopecks: number;
    planned_pickup_min: number;
    planned_delivery_complete_min: number;
  }>;
  unserved_orders: Array<{ order_id: string; reason_code: string; message: string }>;
  ledger: LedgerEntry[];
  ledger_totals_kopecks: Record<string, number>;
  unserved_revenue_exposure_kopecks: number;
  metrics: PlanMetrics;
  validation: { ok: boolean; checks: Array<{ id: string; status: string; message: string }> };
}

export interface PlanComparison {
  same_active_orders: boolean;
  same_served_orders: boolean;
  comparable_cost_saving: boolean;
  cost_delta_kopecks: number;
  cost_saving_kopecks: number;
  cost_saving_pct: number | null;
  revenue_delta_kopecks: number;
  operating_result_delta_kopecks: number;
  margin_delta_pp: number | null;
  empty_distance_delta_m: number;
  notes: string[];
}

export interface PlanChange {
  id: string;
  type: "chain" | "outsource" | "constraint" | "unchanged";
  title: string;
  explanation: string;
  order_ids: string[];
  vehicle_ids: string[];
  route_ids: string[];
  physical_effect: string | null;
  financial_effect_kopecks: number | null;
  financial_effect_scope: string | null;
}

export interface EvaluationResponse {
  schema_version: string;
  run_id: string;
  scenario_hash: string;
  dataset_hash: string;
  input: ScenarioInput;
  effective_parameters: {
    fuel_price_kopecks_per_liter: number;
    fuel_change_pct: number;
    wage_change_pct: number;
    carrier_rate_change_pct: number;
    customer_rate_change_pct: number;
    demand_change_pct: number;
    active_order_count: number;
    base_active_order_count: number;
    disabled_vehicle_ids: string[];
    disabled_driver_ids: string[];
    maintenance_remaining_overrides_m: Record<string, number>;
  };
  active_order_ids: string[];
  original: Plan;
  baseline: Plan;
  market_impact: {
    operating_result_delta_kopecks: number;
    cost_delta_kopecks: number;
    revenue_delta_kopecks: number;
    active_orders_changed: boolean;
    resources_changed: boolean;
    baseline_mode: string;
    notes: string[];
  };
  warnings: Array<{ code: string; message: string }>;
  provenance: {
    dataset_kind: string;
    disclaimer: string;
    cards: ProvenanceCard[];
  };
  computation: {
    engine_version: string;
    elapsed_ms: number;
    dataset_id: string;
    dataset_version: string;
    dataset_hash: string;
  };
}

export interface OptimizationResponse extends EvaluationResponse {
  business_status: "complete" | "infeasible" | "unresolved" | "error";
  optimized: Plan | null;
  comparison: PlanComparison | null;
  changes: PlanChange[];
  diagnostics: Array<{ code: string; message: string; order_ids?: string[]; vehicle_ids?: string[] }>;
  solver: {
    engine: "cp_sat_candidates" | "fallback_local_search";
    solver_status: string;
    solution_quality: string;
    candidate_count: number;
    generated_max_chain_length: number;
    elapsed_ms: number;
    best_bound_kopecks: number | null;
    note: string | null;
  };
}

export interface ProvenanceCard {
  id: string;
  title: string;
  kind: string;
  source_url: string | null;
  country_code: string | null;
  note: string | null;
}

export interface DatasetNode {
  id: string;
  name: string;
  kind: "depot" | "customer" | "hub";
  ui_x: number;
  ui_y: number;
}

export interface DatasetEdge {
  id: string;
  from_node_id: string;
  to_node_id: string;
  distance_m: number;
  travel_time_min: number;
}

export interface DatasetOrder {
  id: string;
  pickup_node_id: string;
  delivery_node_id: string;
  weight_kg: number;
  required_body_type: string;
  sector_tag: string;
  delivery_deadline_min: number;
  base_revenue_kopecks: number;
  outsourcing_allowed: boolean;
  provenance_id: string;
}

export interface DatasetVehicle {
  id: string;
  name: string;
  body_type: string;
  capacity_kg: number;
  assigned_driver_id: string;
  available: boolean;
  maintenance_due_in_m: number;
  maintenance_buffer_m: number;
  fixed_cost_per_horizon_kopecks: number;
}

export interface DatasetDriver {
  id: string;
  available: boolean;
}

export interface DemoDataset {
  metadata: {
    dataset_id: string;
    dataset_version: string;
    dataset_kind: string;
    seed: number;
    planning_start: string;
    horizon_min: number;
    disclaimer: string;
  };
  base_active_count: number;
  base_parameters: { fuel_price_kopecks_per_liter: number };
  nodes: DatasetNode[];
  edges: DatasetEdge[];
  order_pool: DatasetOrder[];
  vehicles: DatasetVehicle[];
  drivers: DatasetDriver[];
  carriers: Array<{ id: string; name: string; max_orders_per_horizon: number }>;
  provenance: ProvenanceCard[];
}

export interface DatasetResponse {
  dataset: DemoDataset;
  dataset_hash: string;
  active_order_ids: string[];
  input_bounds: Record<string, { min: number; max: number; step: number }>;
}

export interface ApiErrorBody {
  error: {
    code: string;
    message: string;
    fields: Array<{ path: string; message: string }>;
    request_id: string;
  };
}

export const LEDGER_LABELS: Record<string, string> = {
  own_fuel: "Топливо своего парка",
  own_wear: "Износ по пробегу",
  driver_fixed_wage: "Фиксированная оплата труда",
  driver_variable_pay: "Переменная оплата труда",
  fleet_fixed_cost: "Владение парком",
  vehicle_activation: "Выпуск машины",
  outsourcing: "Подрядчики",
  cancellation_compensation: "Компенсация за невыполнение",
};

export const EMPTY_SCENARIO: Scenario = {
  fuel_change_pct: 0,
  wage_change_pct: 0,
  carrier_rate_change_pct: 0,
  customer_rate_change_pct: 0,
  demand_change_pct: 0,
  disabled_vehicle_ids: [],
  disabled_driver_ids: [],
  maintenance_remaining_overrides_m: {},
};
