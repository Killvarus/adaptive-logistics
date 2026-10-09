import { useApp } from "../state/AppProvider";
import { formatKm, formatMinute } from "../shared/format";
import type { Leg, Plan } from "../api/types";

export function NetworkView() {
  const { state, selectVehicle } = useApp();
  const dataset = state.dataset?.dataset;
  const result = state.optimized ?? state.evaluated;
  if (!dataset || !result) return null;
  const plan = planByKind(result.original, result.baseline, state.optimized?.optimized ?? null, state.selectedPlanKind);
  const legs = (plan?.routes ?? []).flatMap((route) =>
    state.selectedVehicleId && route.vehicle_id !== state.selectedVehicleId ? [] : route.legs,
  );
  const edgeUse = new Map<string, Leg["kind"]>();
  for (const leg of legs) {
    for (const edgeId of leg.path_edge_ids) {
      const previous = edgeUse.get(edgeId);
      if (previous !== "loaded") edgeUse.set(edgeId, leg.kind);
    }
  }
  const nodeById = new Map(dataset.nodes.map((node) => [node.id, node]));
  const summary = plan?.routes
    .filter((route) => !state.selectedVehicleId || route.vehicle_id === state.selectedVehicleId)
    .map((route) => `${route.vehicle_id}: ${route.order_ids.join(" → ")}; ${formatKm(route.distance_m)}, из них ${formatKm(route.empty_distance_m)} пустыми`)
    .join(" · ");
  return (
    <article className="card">
      <h2>Сеть поставок</h2>
      <div className="filters">
        <label>
          Машина
          <select value={state.selectedVehicleId ?? ""} onChange={(event) => selectVehicle(event.target.value || null)}>
            <option value="">Все</option>
            {dataset.vehicles.map((vehicle) => (
              <option key={vehicle.id} value={vehicle.id}>{vehicle.id}</option>
            ))}
          </select>
        </label>
      </div>
      <div className="network-wrap">
        <svg className="network" viewBox="0 0 900 420" role="img" aria-label="Условная схема сети">
          {dataset.edges.map((edge) => {
            const from = nodeById.get(edge.from_node_id);
            const to = nodeById.get(edge.to_node_id);
            if (!from || !to) return null;
            const used = edgeUse.get(edge.id);
            return (
              <line
                key={edge.id}
                x1={from.ui_x}
                y1={from.ui_y}
                x2={to.ui_x}
                y2={to.ui_y}
                stroke={used === "loaded" ? "#176b62" : used === "empty" ? "#68788e" : "#d5dee8"}
                strokeWidth={used ? 3 : 1}
                strokeDasharray={used === "empty" ? "6 4" : undefined}
              />
            );
          })}
          {dataset.nodes.map((node) => (
            <g key={node.id}>
              {node.kind === "depot" ? (
                <rect x={node.ui_x - 54} y={node.ui_y - 18} width="108" height="36" rx="8" fill="#e6f2ef" stroke="#176b62" />
              ) : (
                <circle cx={node.ui_x} cy={node.ui_y} r={node.kind === "hub" ? 16 : 12} fill="#fff" stroke="#176b62" strokeWidth="2" />
              )}
              <text x={node.ui_x} y={node.ui_y + (node.kind === "depot" ? 4 : 32)} textAnchor="middle" fontSize="12" fill="#17212f">
                {node.name}
              </text>
            </g>
          ))}
        </svg>
      </div>
      <div className="legend">
        <span><i className="swatch" />Гружёный участок</span>
        <span><i className="swatch empty" />Пустой участок</span>
        <span>Условная сеть, не навигационная карта</span>
      </div>
      <p className="hint">{summary || "Маршрут появится после расчёта."} {dataset.metadata.planning_start ? "" : ""}</p>
      {plan && plan.routes[0] && (
        <p className="hint">
          Пример времени: выезд {formatMinute(dataset.metadata.planning_start, plan.routes[0].start_min)}, возврат {formatMinute(dataset.metadata.planning_start, plan.routes[0].finish_min)}.
        </p>
      )}
    </article>
  );
}

function planByKind(a: Plan, b: Plan, c: Plan | null, kind: "A" | "B" | "C"): Plan {
  if (kind === "A") return a;
  if (kind === "C" && c) return c;
  return b;
}
