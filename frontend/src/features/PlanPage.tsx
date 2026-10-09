import { useMemo, useState } from "react";
import type { Plan, Route } from "../api/types";
import { useApp } from "../state/AppProvider";
import { formatKm, formatMinute, formatRub, formatWeight } from "../shared/format";

export function PlanPage() {
  const { state, selectPlan, selectOrder } = useApp();
  const result = state.optimized ?? state.evaluated;
  const dataset = state.dataset?.dataset;
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState<"id" | "deadline" | "revenue">("id");
  if (!result || !dataset) return <p>План появится после расчёта.</p>;
  const plan = state.selectedPlanKind === "A" ? result.original : state.selectedPlanKind === "C" && state.optimized?.optimized ? state.optimized.optimized : result.baseline;
  const orders = useMemo(() => {
    const ids = new Set([
      ...plan.routes.flatMap((route) => route.order_ids),
      ...plan.outsourced_assignments.map((item) => item.order_id),
      ...plan.unserved_orders.map((item) => item.order_id),
    ]);
    const rows = dataset.order_pool.filter((order) => ids.has(order.id));
    const filtered = rows.filter((order) => {
      const text = `${order.id} ${order.pickup_node_id} ${order.delivery_node_id}`.toLowerCase();
      return text.includes(query.toLowerCase());
    });
    return filtered.sort((a, b) => {
      if (sort === "deadline") return a.delivery_deadline_min - b.delivery_deadline_min;
      if (sort === "revenue") return a.base_revenue_kopecks - b.base_revenue_kopecks;
      return a.id.localeCompare(b.id);
    });
  }, [dataset.order_pool, plan, query, sort]);
  const routeByOrder = new Map<string, Route>();
  for (const route of plan.routes) for (const orderId of route.order_ids) routeByOrder.set(orderId, route);
  const outByOrder = new Map(plan.outsourced_assignments.map((item) => [item.order_id, item]));
  const unserved = new Map(plan.unserved_orders.map((item) => [item.order_id, item]));
  const horizon = dataset.metadata.horizon_min;
  return (
    <section>
      <h2 className="page-title">План перевозок</h2>
      <p className="hint">Расписание построено по условным временам сети. Смена с {formatMinute(dataset.metadata.planning_start, 0)}.</p>
      <div className="plans">
        {(["A", "B", "C"] as const).map((kind) => (
          <button key={kind} className={state.selectedPlanKind === kind ? "active" : ""} disabled={kind === "C" && !state.optimized?.optimized} onClick={() => selectPlan(kind)}>
            {kind}
          </button>
        ))}
        <span className="badge">{plan.service_status === "complete" ? "Все обязательные заказы назначены" : "Часть заказов не назначена"}</span>
      </div>
      <article className="card" style={{ marginBottom: 16 }}>
        <h2>Машины и цепочки</h2>
        <div className="timeline">
          {dataset.vehicles.map((vehicle) => {
            const route = plan.routes.find((item) => item.vehicle_id === vehicle.id);
            const driverOff = result.input.scenario.disabled_driver_ids.includes(vehicle.assigned_driver_id);
            return (
              <div key={vehicle.id}>
                <strong>{vehicle.id}</strong> · {vehicle.name} · {vehicle.assigned_driver_id}
                {!route && <div className="hint">{driverOff ? `Недоступна: водитель ${vehicle.assigned_driver_id} отсутствует.` : "Не назначена; фиксированные затраты сохраняются."}</div>}
                {route && (
                  <>
                    <div className="hint">{route.order_ids.join(" → ")} · {formatKm(route.distance_m)} · {formatKm(route.empty_distance_m)} пустыми · запас до ТО {formatKm(route.maintenance_slack_m)}</div>
                    <div className="bar" title={`${formatMinute(dataset.metadata.planning_start, route.start_min)}–${formatMinute(dataset.metadata.planning_start, route.finish_min)}`}>
                      {route.legs.map((leg, index) => (
                        <div key={`${leg.depart_min}-${index}`} className={`seg ${leg.kind}`} style={segmentStyle(leg.depart_min, leg.arrive_min, horizon)} title={`${leg.from_node_id} → ${leg.to_node_id}, ${leg.kind === "loaded" ? "груз" : "пусто"}`} />
                      ))}
                      {route.events.map((event, index) => (
                        <div key={`${event.type}-${index}`} className={`seg ${event.type === "wait" ? "wait" : "service"}`} style={segmentStyle(event.start_min, event.finish_min, horizon)} title={`${event.type} ${event.order_id} ${formatMinute(dataset.metadata.planning_start, event.start_min)}`} />
                      ))}
                    </div>
                  </>
                )}
              </div>
            );
          })}
        </div>
      </article>
      <article className="card">
        <h2>Заказы</h2>
        <div className="filters">
          <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="ID или направление" aria-label="Фильтр заказов" />
          <select value={sort} onChange={(event) => setSort(event.target.value as typeof sort)} aria-label="Сортировка">
            <option value="id">ID</option>
            <option value="deadline">Срок</option>
            <option value="revenue">Выручка</option>
          </select>
        </div>
        <div style={{ overflow: "auto" }}>
          <table>
            <thead>
              <tr>
                <th>ID</th>
                <th>Откуда → куда</th>
                <th>Груз</th>
                <th>Срок</th>
                <th className="num">Выручка</th>
                <th>Назначение</th>
                <th>Статус</th>
              </tr>
            </thead>
            <tbody>
              {orders.length === 0 && (
                <tr><td colSpan={7}>Подходящих заказов нет. Сбросить фильтр можно очисткой поля.</td></tr>
              )}
              {orders.map((order) => {
                const route = routeByOrder.get(order.id);
                const external = outByOrder.get(order.id);
                const missed = unserved.get(order.id);
                return (
                  <tr key={order.id} onClick={() => selectOrder(order.id)} style={{ cursor: "pointer" }}>
                    <td>{order.id}</td>
                    <td>{order.pickup_node_id} → {order.delivery_node_id}</td>
                    <td>{formatWeight(order.weight_kg)} · {order.required_body_type}</td>
                    <td className="nums">{formatMinute(dataset.metadata.planning_start, order.delivery_deadline_min)}</td>
                    <td className="num nums">{formatRub(order.base_revenue_kopecks)}</td>
                    <td>{route ? route.vehicle_id : external ? `Подрядчик ${external.carrier_id}` : "нет"}</td>
                    <td>{missed ? missed.message : route ? `Цепочка ${route.id}` : external ? formatRub(external.price_kopecks) : "—"}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        {state.selectedOrderId && <OrderDrawer orderId={state.selectedOrderId} plan={plan} />}
      </article>
    </section>
  );
}

function segmentStyle(start: number, finish: number, horizon: number) {
  const left = (start / horizon) * 100;
  const width = Math.max(((finish - start) / horizon) * 100, 0.8);
  return { left: `${left}%`, width: `${width}%` };
}

function OrderDrawer({ orderId, plan }: { orderId: string; plan: Plan }) {
  const { state, selectOrder } = useApp();
  const order = state.dataset?.dataset.order_pool.find((item) => item.id === orderId);
  const route = plan.routes.find((item) => item.order_ids.includes(orderId));
  if (!order) return null;
  return (
    <div className="drawer-backdrop" onClick={() => selectOrder(null)} role="presentation">
      <aside className="drawer" role="dialog" aria-label={`Заказ ${orderId}`} onClick={(event) => event.stopPropagation()} onKeyDown={(event) => { if (event.key === "Escape") selectOrder(null); }}>
        <button className="btn" onClick={() => selectOrder(null)}>Закрыть</button>
        <h2>{order.id}</h2>
        <p>{order.pickup_node_id} → {order.delivery_node_id}</p>
        <p>{formatWeight(order.weight_kg)}, {order.required_body_type}, {order.sector_tag}</p>
        <p>Выручка перевозки: {formatRub(order.base_revenue_kopecks)}</p>
        <p>Происхождение: {order.provenance_id}</p>
        {route && (
          <>
            <p>Цепочка {route.id}: {route.order_ids.join(" → ")}. Переменная стоимость цепочки {formatRub(route.variable_cost_kopecks)}. Это не точная себестоимость одного заказа.</p>
            <ul>
              {route.events.filter((event) => event.order_id === order.id).map((event) => (
                <li key={`${event.type}-${event.start_min}`}>{event.type}: {event.start_min}–{event.finish_min} мин</li>
              ))}
            </ul>
          </>
        )}
      </aside>
    </div>
  );
}
