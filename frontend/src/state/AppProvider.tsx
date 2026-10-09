import { createContext, useContext, useEffect, useMemo, useReducer, useRef, type ReactNode } from "react";
import { evaluateScenario, fetchDemoDataset, optimizeScenario } from "../api/client";
import {
  EMPTY_SCENARIO,
  type DatasetResponse,
  type EvaluationResponse,
  type OptimizationResponse,
  type PlanKind,
  type Scenario,
  type ScenarioInput,
  type View,
} from "../api/types";
import { canonicalScenario } from "../shared/format";

const STORAGE_KEY = "logus-demo-scenario-v1";

type Status = "idle" | "loading" | "success" | "error";

interface State {
  view: View;
  dataset: DatasetResponse | null;
  draft: ScenarioInput | null;
  evaluated: EvaluationResponse | null;
  optimized: OptimizationResponse | null;
  selectedPlanKind: PlanKind;
  selectedVehicleId: string | null;
  selectedOrderId: string | null;
  selectedRouteId: string | null;
  datasetStatus: Status;
  evaluationStatus: Status;
  optimizationStatus: Status;
  error: string | null;
}

type Action =
  | { type: "dataset"; dataset: DatasetResponse; draft: ScenarioInput }
  | { type: "dataset-error"; message: string }
  | { type: "view"; view: View }
  | { type: "draft"; scenario: Scenario }
  | { type: "eval-start" }
  | { type: "eval-ok"; result: EvaluationResponse }
  | { type: "opt-start" }
  | { type: "opt-ok"; result: OptimizationResponse }
  | { type: "failed"; message: string; kind: "eval" | "opt" }
  | { type: "select-plan"; kind: PlanKind }
  | { type: "select-vehicle"; id: string | null }
  | { type: "select-order"; id: string | null }
  | { type: "select-route"; id: string | null }
  | { type: "reset-draft" };

const initial: State = {
  view: readView(),
  dataset: null,
  draft: null,
  evaluated: null,
  optimized: null,
  selectedPlanKind: "B",
  selectedVehicleId: null,
  selectedOrderId: null,
  selectedRouteId: null,
  datasetStatus: "loading",
  evaluationStatus: "idle",
  optimizationStatus: "idle",
  error: null,
};

function reducer(state: State, action: Action): State {
  switch (action.type) {
    case "dataset":
      return { ...state, dataset: action.dataset, draft: action.draft, datasetStatus: "success", error: null };
    case "dataset-error":
      return { ...state, datasetStatus: "error", error: action.message };
    case "view":
      return { ...state, view: action.view };
    case "draft":
      return state.draft ? { ...state, draft: { ...state.draft, scenario: action.scenario } } : state;
    case "eval-start":
      return { ...state, evaluationStatus: "loading", error: null };
    case "eval-ok":
      return {
        ...state,
        evaluated: action.result,
        optimized: null,
        evaluationStatus: "success",
        selectedPlanKind: "B",
        error: null,
      };
    case "opt-start":
      return { ...state, optimizationStatus: "loading", error: null };
    case "opt-ok":
      return {
        ...state,
        evaluated: action.result,
        optimized: action.result,
        optimizationStatus: "success",
        evaluationStatus: "success",
        selectedPlanKind: action.result.optimized ? "C" : "B",
        error: null,
      };
    case "failed":
      return {
        ...state,
        error: action.message,
        evaluationStatus: action.kind === "eval" ? "error" : state.evaluationStatus,
        optimizationStatus: action.kind === "opt" ? "error" : state.optimizationStatus,
      };
    case "select-plan":
      return { ...state, selectedPlanKind: action.kind };
    case "select-vehicle":
      return { ...state, selectedVehicleId: action.id };
    case "select-order":
      return { ...state, selectedOrderId: action.id, selectedRouteId: action.id ? state.selectedRouteId : null };
    case "select-route":
      return { ...state, selectedRouteId: action.id };
    case "reset-draft":
      return state.draft
        ? {
            ...state,
            draft: { ...state.draft, scenario: { ...EMPTY_SCENARIO } },
            optimized: null,
            selectedVehicleId: null,
            selectedOrderId: null,
            selectedRouteId: null,
          }
        : state;
    default:
      return state;
  }
}

interface AppContextValue {
  state: State;
  stale: boolean;
  setView: (view: View) => void;
  updateScenario: (patch: Partial<Scenario>) => void;
  setMaintenance: (vehicleId: string, meters: number | null) => void;
  toggleId: (field: "disabled_vehicle_ids" | "disabled_driver_ids", id: string) => void;
  applyPreset: (scenario: Scenario) => void;
  recalculate: () => void;
  adapt: () => void;
  reset: () => void;
  selectPlan: (kind: PlanKind) => void;
  selectVehicle: (id: string | null) => void;
  selectOrder: (id: string | null) => void;
  selectRoute: (id: string | null) => void;
}

const AppContext = createContext<AppContextValue | null>(null);

export function AppProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(reducer, initial);
  const revision = useRef(0);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    fetchDemoDataset(controller.signal)
      .then((dataset) => {
        const draft = loadDraft(dataset) ?? inputFrom(dataset, EMPTY_SCENARIO);
        dispatch({ type: "dataset", dataset, draft });
      })
      .catch((error: Error) => {
        if (error.name === "AbortError") return;
        dispatch({ type: "dataset-error", message: error.message });
      });
    return () => controller.abort();
  }, []);

  useEffect(() => {
    if (!state.draft || state.evaluated || state.evaluationStatus === "loading") return;
    if (state.datasetStatus !== "success") return;
    void run("eval", state.draft);
    // Initial calculation only.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state.datasetStatus, state.draft?.dataset_id]);

  useEffect(() => {
    if (!state.draft || state.draft.dataset_id !== "demo_ru_regional_01") return;
    localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({
        dataset_version: state.draft.dataset_version,
        scenario: state.draft.scenario,
      }),
    );
  }, [state.draft]);

  function run(kind: "eval" | "opt", input: ScenarioInput) {
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    const id = ++revision.current;
    dispatch({ type: kind === "eval" ? "eval-start" : "opt-start" });
    const call = kind === "eval" ? evaluateScenario(input, controller.signal) : optimizeScenario(input, controller.signal);
    return call
      .then((result) => {
        if (id !== revision.current) return;
        if (kind === "eval") dispatch({ type: "eval-ok", result });
        else dispatch({ type: "opt-ok", result: result as OptimizationResponse });
      })
      .catch((error: Error) => {
        if (error.name === "AbortError" || id !== revision.current) return;
        dispatch({ type: "failed", kind, message: error.message });
      });
  }

  const stale = useMemo(() => {
    if (!state.draft) return false;
    const snapshot = state.optimized?.input ?? state.evaluated?.input;
    if (!snapshot) return false;
    return canonicalScenario(state.draft) !== canonicalScenario(snapshot);
  }, [state.draft, state.evaluated, state.optimized]);

  const value: AppContextValue = {
    state,
    stale,
    setView: (view) => {
      const url = new URL(window.location.href);
      url.searchParams.set("view", view);
      window.history.replaceState(null, "", url);
      dispatch({ type: "view", view });
    },
    updateScenario: (patch) => {
      if (!state.draft) return;
      dispatch({ type: "draft", scenario: { ...state.draft.scenario, ...patch } });
    },
    setMaintenance: (vehicleId, meters) => {
      if (!state.draft) return;
      const next = { ...state.draft.scenario.maintenance_remaining_overrides_m };
      if (meters === null) delete next[vehicleId];
      else next[vehicleId] = meters;
      dispatch({
        type: "draft",
        scenario: { ...state.draft.scenario, maintenance_remaining_overrides_m: next },
      });
    },
    toggleId: (field, id) => {
      if (!state.draft) return;
      const current = new Set(state.draft.scenario[field]);
      if (current.has(id)) current.delete(id);
      else current.add(id);
      dispatch({ type: "draft", scenario: { ...state.draft.scenario, [field]: [...current].sort() } });
    },
    applyPreset: (scenario) => dispatch({ type: "draft", scenario }),
    recalculate: () => {
      if (state.draft) void run("eval", state.draft);
    },
    adapt: () => {
      if (state.draft) void run("opt", state.draft);
    },
    reset: () => {
      dispatch({ type: "reset-draft" });
      if (state.dataset) {
        const input = inputFrom(state.dataset, EMPTY_SCENARIO);
        dispatch({ type: "draft", scenario: EMPTY_SCENARIO });
        void run("eval", input);
      }
    },
    selectPlan: (kind) => dispatch({ type: "select-plan", kind }),
    selectVehicle: (id) => dispatch({ type: "select-vehicle", id }),
    selectOrder: (id) => dispatch({ type: "select-order", id }),
    selectRoute: (id) => dispatch({ type: "select-route", id }),
  };

  return <AppContext.Provider value={value}>{children}</AppContext.Provider>;
}

export function useApp(): AppContextValue {
  const value = useContext(AppContext);
  if (!value) throw new Error("useApp outside provider");
  return value;
}

function inputFrom(dataset: DatasetResponse, scenario: Scenario): ScenarioInput {
  return {
    dataset_id: dataset.dataset.metadata.dataset_id,
    dataset_version: dataset.dataset.metadata.dataset_version,
    objective: "min_cost_with_full_service",
    scenario,
  };
}

function loadDraft(dataset: DatasetResponse): ScenarioInput | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const saved = JSON.parse(raw) as { dataset_version?: string; scenario?: Scenario };
    if (saved.dataset_version !== dataset.dataset.metadata.dataset_version || !saved.scenario) return null;
    return inputFrom(dataset, { ...EMPTY_SCENARIO, ...saved.scenario });
  } catch {
    return null;
  }
}

function readView(): View {
  const value = new URLSearchParams(window.location.search).get("view");
  if (value === "plan" || value === "data" || value === "overview") return value;
  return "overview";
}
