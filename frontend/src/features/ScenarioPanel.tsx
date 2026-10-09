import { EMPTY_SCENARIO, type Scenario } from "../api/types";
import { useApp } from "../state/AppProvider";

const BOUNDS = {
  fuel_change_pct: { min: -20, max: 60, step: 5, label: "Топливо" },
  wage_change_pct: { min: 0, max: 40, step: 5, label: "Оплата труда" },
  carrier_rate_change_pct: { min: -10, max: 50, step: 5, label: "Услуги подрядчиков" },
  customer_rate_change_pct: { min: -20, max: 10, step: 5, label: "Тариф клиента" },
  demand_change_pct: { min: -30, max: 30, step: 5, label: "Число заказов" },
} as const;

export function ScenarioPanel() {
  const { state, stale, updateScenario, toggleId, setMaintenance, applyPreset, recalculate, adapt, reset } = useApp();
  const scenario = state.draft?.scenario;
  const busy = state.evaluationStatus === "loading" || state.optimizationStatus === "loading";
  const dataset = state.dataset?.dataset;
  if (!scenario || !dataset) {
    return <aside className="scenario">Параметры появятся после загрузки набора.</aside>;
  }
  const presets: Array<{ id: string; label: string; scenario: Scenario }> = [
    { id: "base", label: "Исходные условия", scenario: { ...EMPTY_SCENARIO } },
    {
      id: "cost_pressure",
      label: "Рост расходов",
      scenario: { ...EMPTY_SCENARIO, fuel_change_pct: 25, wage_change_pct: 10, carrier_rate_change_pct: 10 },
    },
    {
      id: "margin_squeeze",
      label: "Сжатие маржи",
      scenario: {
        ...EMPTY_SCENARIO,
        fuel_change_pct: 25,
        wage_change_pct: 10,
        carrier_rate_change_pct: 10,
        customer_rate_change_pct: -5,
        demand_change_pct: -20,
      },
    },
    {
      id: "resource_shortage",
      label: "Недоступен водитель",
      scenario: { ...EMPTY_SCENARIO, disabled_driver_ids: ["D-02"] },
    },
    {
      id: "maintenance_limit",
      label: "Машина близка к ТО",
      scenario: { ...EMPTY_SCENARIO, maintenance_remaining_overrides_m: { "V-01": 300_000 } },
    },
    {
      id: "infeasible",
      label: "Недостаточно мощности",
      scenario: { ...EMPTY_SCENARIO, disabled_driver_ids: ["D-03"] },
    },
  ];
  const ordersNow = state.evaluated?.effective_parameters.active_order_count;
  const ordersBase = dataset.base_active_count;
  return (
    <aside className="scenario">
      <h2 style={{ marginTop: 0, fontSize: 17 }}>Сценарий</h2>
      <div className="preset-row">
        {presets.map((preset) => (
          <button key={preset.id} className="btn" onClick={() => applyPreset(preset.scenario)} disabled={busy}>
            {preset.label}
          </button>
        ))}
      </div>
      <p className="hint">Проценты — параметры стресс-теста, не статистика рынка.</p>
      <div className="group-title">Расходы</div>
      <Slider name="fuel_change_pct" value={scenario.fuel_change_pct} onChange={updateScenario} disabled={busy} />
      <p className="hint">
        База {(dataset.base_parameters.fuel_price_kopecks_per_liter / 100).toLocaleString("ru-RU")} ₽/л
        {state.evaluated && !stale
          ? ` → ${(state.evaluated.effective_parameters.fuel_price_kopecks_per_liter / 100).toLocaleString("ru-RU")} ₽/л`
          : ". Цена после пересчёта."}
      </p>
      <Slider name="wage_change_pct" value={scenario.wage_change_pct} onChange={updateScenario} disabled={busy} />
      <Slider name="carrier_rate_change_pct" value={scenario.carrier_rate_change_pct} onChange={updateScenario} disabled={busy} />
      <div className="group-title">Доходы и спрос</div>
      <Slider name="customer_rate_change_pct" value={scenario.customer_rate_change_pct} onChange={updateScenario} disabled={busy} />
      <Slider name="demand_change_pct" value={scenario.demand_change_pct} onChange={updateScenario} disabled={busy} />
      <p className="hint">
        {ordersBase} → {stale || ordersNow === undefined ? "…" : ordersNow} заказов. Меняется число заявок, не вес каждой.
      </p>
      <div className="group-title">Ресурсы</div>
      {dataset.vehicles.map((vehicle) => {
        const driverOff = scenario.disabled_driver_ids.includes(vehicle.assigned_driver_id);
        const vehicleOff = scenario.disabled_vehicle_ids.includes(vehicle.id);
        return (
          <div key={vehicle.id} className="check">
            <input
              type="checkbox"
              checked={!vehicleOff}
              onChange={() => toggleId("disabled_vehicle_ids", vehicle.id)}
              disabled={busy}
            />
            <div>
              <div>
                {vehicle.id} · {vehicle.name}
              </div>
              <label className="hint">
                <input
                  type="checkbox"
                  checked={!driverOff}
                  onChange={() => toggleId("disabled_driver_ids", vehicle.assigned_driver_id)}
                  disabled={busy}
                />{" "}
                водитель {vehicle.assigned_driver_id} {driverOff ? "отсутствует" : "доступен"}
              </label>
              {driverOff && !vehicleOff && (
                <div className="hint">Машина исправна, но недоступна для плана: водитель {vehicle.assigned_driver_id} отсутствует.</div>
              )}
              <label className="hint">
                Остаток до ТО, км
                <input
                  type="number"
                  min={0}
                  step={10}
                  value={
                    scenario.maintenance_remaining_overrides_m[vehicle.id] !== undefined
                      ? scenario.maintenance_remaining_overrides_m[vehicle.id] / 1000
                      : ""
                  }
                  placeholder={String(vehicle.maintenance_due_in_m / 1000)}
                  onChange={(event) => {
                    const text = event.target.value;
                    setMaintenance(vehicle.id, text === "" ? null : Math.round(Number(text) * 1000));
                  }}
                  disabled={busy}
                />
              </label>
            </div>
          </div>
        );
      })}
      <div className="actions">
        <button className="btn" onClick={recalculate} disabled={busy || !state.draft}>
          {state.evaluationStatus === "loading" ? "Считаем влияние…" : "Пересчитать влияние"}
        </button>
        <button className="btn-primary" onClick={adapt} disabled={busy || !state.draft}>
          {state.optimizationStatus === "loading" ? "Ищем допустимые цепочки…" : "Найти план адаптации"}
        </button>
        <button className="btn-ghost" onClick={reset} disabled={busy}>Сбросить изменения</button>
      </div>
    </aside>
  );
}

function Slider({
  name,
  value,
  onChange,
  disabled,
}: {
  name: keyof typeof BOUNDS;
  value: number;
  onChange: (patch: Partial<Scenario>) => void;
  disabled: boolean;
}) {
  const bound = BOUNDS[name];
  return (
    <div className="field">
      <label>
        <span>{bound.label}</span>
        <input
          type="number"
          min={bound.min}
          max={bound.max}
          step={bound.step}
          value={value}
          disabled={disabled}
          onChange={(event) => onChange({ [name]: Number(event.target.value) })}
        />
      </label>
      <input
        type="range"
        min={bound.min}
        max={bound.max}
        step={bound.step}
        value={value}
        disabled={disabled}
        onChange={(event) => onChange({ [name]: Number(event.target.value) })}
        aria-label={bound.label}
      />
      <div className="hint">{value > 0 ? `+${value}` : value}% относительно базового значения</div>
    </div>
  );
}
