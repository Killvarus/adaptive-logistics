import { Bar, BarChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { LEDGER_LABELS, type Plan, type PlanKind } from "../api/types";
import { useApp } from "../state/AppProvider";
import { formatKm, formatPct, formatRub, formatShare, formatSignedRub } from "../shared/format";
import { NetworkView } from "./NetworkView";

const COLORS: Record<string, string> = {
  own_fuel: "#176b62",
  own_wear: "#3d8b7a",
  driver_fixed_wage: "#2457c5",
  driver_variable_pay: "#8eace0",
  fleet_fixed_cost: "#68788e",
  vehicle_activation: "#9aa8b8",
  outsourcing: "#c77819",
  cancellation_compensation: "#b42318",
};

export function Overview() {
  const { state, stale, selectPlan } = useApp();
  const result = state.optimized ?? state.evaluated;
  if (!result) {
    return <p>{state.evaluationStatus === "error" ? state.error : "Считаем исходный план."}</p>;
  }
  const plans: Array<Plan | null> = [result.original, result.baseline, state.optimized?.optimized ?? null];
  const selected = selectedPlan(plans, state.selectedPlanKind);
  const metrics = selected?.metrics;
  return (
    <section>
      <h2 className="page-title">Обзор смены</h2>
      <p className="lede">
        A — исходные условия и базовая политика. B — те же правила при новых параметрах. C — цепочки и выбор транспорта при тех же заказах, что у B.
      </p>
      {stale && (
        <div className="banner">
          <span>Параметры изменены. Ниже — результат предыдущего расчёта.</span>
          <span className="badge">Нужен пересчёт</span>
        </div>
      )}
      {state.error && <div className="banner error">{state.error}</div>}
      {state.optimized?.business_status === "infeasible" && (
        <div className="banner error">
          В текущих ограничениях и вариантах маршрутов полный план не найден.
          {state.optimized.diagnostics[0] ? ` ${state.optimized.diagnostics[0].message}` : ""}
        </div>
      )}
      {state.optimized?.business_status === "unresolved" && (
        <div className="banner">За отведённый поиск новый полный план не найден.</div>
      )}
      <div className="plans" role="tablist" aria-label="Состояние плана">
        <PlanButton kind="A" label="A · исходно" active={state.selectedPlanKind === "A"} onClick={selectPlan} />
        <PlanButton kind="B" label="B · рынок изменился" active={state.selectedPlanKind === "B"} onClick={selectPlan} />
        <PlanButton kind="C" label="C · адаптация" active={state.selectedPlanKind === "C"} disabled={!state.optimized?.optimized} onClick={selectPlan} />
      </div>
      <div className="kpis">
        <Kpi title="Расчётный операционный результат" hint="Доход от выполненных перевозок минус включённые в модель расходы за смену; не бухгалтерская отчётность." value={metrics ? formatRub(metrics.operating_result_kopecks) : "—"} loss={!!metrics && metrics.operating_result_kopecks < 0} />
        <Kpi title="Маржинальность" hint="Процент от признанной выручки. Прочерк, если выручки нет." value={metrics ? formatPct(metrics.margin_pct, 1) : "—"} />
        <Kpi title="Затраты" hint="Сумма статей ledger." value={metrics ? formatRub(metrics.total_cost_kopecks) : "—"} />
        <Kpi title="Сервис" hint="Выполненные обязательные заказы." value={metrics ? (metrics.service_rate === null ? "Нет заказов" : `${metrics.served_orders}/${metrics.total_orders}`) : "—"} />
      </div>
      <p className="hint">
        При новых условиях результат изменился с {formatRub(result.original.metrics.operating_result_kopecks)} до {formatRub(result.baseline.metrics.operating_result_kopecks)}.
        {state.optimized?.optimized
          ? ` Перестройка плана дала ${formatRub(state.optimized.optimized.metrics.operating_result_kopecks)}.`
          : state.optimized?.business_status === "infeasible"
            ? " Полный план адаптации не найден."
            : state.optimized?.business_status === "unresolved"
              ? " За отведённое время новый полный план не найден."
              : " План адаптации ещё не рассчитан."}
      </p>
      <div className="grid-2">
        <div className="stack">
          <NetworkView />
          <CostChart plans={plans} />
        </div>
        <div className="stack">
          <Comparison />
          <Changes />
        </div>
      </div>
    </section>
  );
}

function PlanButton({ kind, label, active, disabled, onClick }: { kind: PlanKind; label: string; active: boolean; disabled?: boolean; onClick: (kind: PlanKind) => void }) {
  return (
    <button className={active ? "active" : ""} disabled={disabled} onClick={() => onClick(kind)}>
      {label}
    </button>
  );
}

function Kpi({ title, hint, value, loss }: { title: string; hint: string; value: string; loss?: boolean }) {
  return (
    <article className="card">
      <div className="kpi-label" title={hint}>{title}</div>
      <div className={`kpi-value nums ${loss ? "loss" : ""}`}>{value}</div>
      {loss && <div className="kpi-note">Убыток в модели</div>}
    </article>
  );
}

function CostChart({ plans }: { plans: Array<Plan | null> }) {
  const present = plans.filter((plan): plan is Plan => plan !== null);
  const categories = Object.keys(LEDGER_LABELS).filter((key) => present.some((plan) => (plan.ledger_totals_kopecks[key] ?? 0) !== 0));
  const data = present.map((plan) => {
    const row: Record<string, string | number> = { name: plan.kind };
    for (const key of categories) row[key] = (plan.ledger_totals_kopecks[key] ?? 0) / 100;
    return row;
  });
  return (
    <article className="card">
      <h2>Из чего состоят расходы</h2>
      <p className="hint">За выбранную смену, ₽. Сумма сегментов равна полной стоимости.</p>
      {present.length < 3 && <p className="hint">Колонка C появится после поиска адаптации, не как нулевые затраты.</p>}
      <div style={{ width: "100%", height: 220 }}>
        <ResponsiveContainer>
          <BarChart data={data} layout="vertical" margin={{ left: 16, right: 8 }}>
            <XAxis type="number" tickFormatter={(value) => new Intl.NumberFormat("ru-RU").format(Number(value))} />
            <YAxis type="category" dataKey="name" width={28} />
            <Tooltip formatter={(value, name) => [formatRub(Math.round(Number(value) * 100)), LEDGER_LABELS[String(name)] ?? String(name)]} />
            {categories.map((key) => (
              <Bar key={key} dataKey={key} stackId="cost" fill={COLORS[key]} name={key} />
            ))}
          </BarChart>
        </ResponsiveContainer>
      </div>
      <div className="legend">
        {categories.map((key) => (
          <span key={key}><i className="swatch" style={{ borderColor: COLORS[key] }} />{LEDGER_LABELS[key]}</span>
        ))}
      </div>
    </article>
  );
}

function Comparison() {
  const { state } = useApp();
  const result = state.optimized ?? state.evaluated;
  if (!result) return null;
  const c = state.optimized?.optimized ?? null;
  const comparison = state.optimized?.comparison ?? null;
  const rows = [
    ["Выручка", result.original.metrics.recognized_revenue_kopecks, result.baseline.metrics.recognized_revenue_kopecks, c?.metrics.recognized_revenue_kopecks, comparison ? formatSignedRub(comparison.revenue_delta_kopecks) : "—"],
    ["Затраты", result.original.metrics.total_cost_kopecks, result.baseline.metrics.total_cost_kopecks, c?.metrics.total_cost_kopecks, comparison ? formatSignedRub(comparison.cost_delta_kopecks) : "—"],
    ["Результат", result.original.metrics.operating_result_kopecks, result.baseline.metrics.operating_result_kopecks, c?.metrics.operating_result_kopecks, comparison ? formatSignedRub(comparison.operating_result_delta_kopecks) : "—"],
  ] as const;
  return (
    <article className="card">
      <h2>Сравнение A / B / C</h2>
      {comparison && !comparison.comparable_cost_saving && <p className="hint">{comparison.notes[0]}</p>}
      {comparison?.comparable_cost_saving && comparison.cost_saving_pct !== null && (
        <p className="hint">Сопоставимое снижение затрат C относительно B: {formatPct(comparison.cost_saving_pct, 1)}.</p>
      )}
      <table>
        <thead>
          <tr>
            <th>Показатель</th>
            <th className="num">A</th>
            <th className="num">B</th>
            <th className="num">C</th>
            <th className="num">C−B</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(([label, a, b, cValue, delta]) => (
            <tr key={label}>
              <td>{label}</td>
              <td className="num nums">{formatRub(a)}</td>
              <td className="num nums">{formatRub(b)}</td>
              <td className="num nums">{cValue === undefined ? "—" : formatRub(cValue)}</td>
              <td className="num nums">{delta}</td>
            </tr>
          ))}
          <tr>
            <td>Маржинальность</td>
            <td className="num">{formatPct(result.original.metrics.margin_pct, 1)}</td>
            <td className="num">{formatPct(result.baseline.metrics.margin_pct, 1)}</td>
            <td className="num">{c ? formatPct(c.metrics.margin_pct, 1) : "—"}</td>
            <td className="num">{comparison?.margin_delta_pp === null || comparison?.margin_delta_pp === undefined ? "—" : `${comparison.margin_delta_pp > 0 ? "+" : ""}${comparison.margin_delta_pp.toLocaleString("ru-RU", { maximumFractionDigits: 2 })} п.п.`}</td>
          </tr>
          <tr>
            <td>Пустой пробег</td>
            <td className="num">{formatKm(result.original.metrics.own_empty_distance_m)}</td>
            <td className="num">{formatKm(result.baseline.metrics.own_empty_distance_m)}</td>
            <td className="num">{c ? formatKm(c.metrics.own_empty_distance_m) : "—"}</td>
            <td className="num">{comparison ? formatKm(comparison.empty_distance_delta_m) : "—"}</td>
          </tr>
          <tr>
            <td>Доля гружёного</td>
            <td className="num">{formatShare(result.original.metrics.own_loaded_distance_share)}</td>
            <td className="num">{formatShare(result.baseline.metrics.own_loaded_distance_share)}</td>
            <td className="num">{c ? formatShare(c.metrics.own_loaded_distance_share) : "—"}</td>
            <td className="num">—</td>
          </tr>
        </tbody>
      </table>
      {result.baseline.baseline_mode_reason && <p className="hint">{result.baseline.baseline_mode_reason}</p>}
    </article>
  );
}

function Changes() {
  const changes = useApp().state.optimized?.changes ?? [];
  const visible = changes.slice(0, 4);
  return (
    <article className="card">
      <h2>Изменения плана</h2>
      {visible.length === 0 && <p className="hint">Появятся после поиска адаптации. Пустой список не заполняется советами.</p>}
      {visible.map((change) => (
        <div key={change.id} className="change" style={{ marginBottom: 12 }}>
          <h3>{change.title}</h3>
          <p>{change.explanation}</p>
          {change.physical_effect && <p>{change.physical_effect}</p>}
          {change.financial_effect_kopecks === null && change.type !== "unchanged" && (
            <p className="hint">Денежный эффект этой карточки не изолирован от остальных изменений.</p>
          )}
        </div>
      ))}
    </article>
  );
}

function selectedPlan(plans: Array<Plan | null>, kind: PlanKind): Plan | null {
  if (kind === "A") return plans[0];
  if (kind === "B") return plans[1];
  return plans[2] ?? plans[1];
}
