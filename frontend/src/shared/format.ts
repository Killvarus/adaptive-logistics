import type { Scenario, ScenarioInput } from "../api/types";

export function formatRub(kopecks: number, digits = 0): string {
  return new Intl.NumberFormat("ru-RU", {
    style: "currency",
    currency: "RUB",
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(kopecks / 100);
}

export function formatSignedRub(kopecks: number): string {
  const text = formatRub(Math.abs(kopecks), 0);
  if (kopecks > 0) return `+${text}`;
  if (kopecks < 0) return `−${text}`;
  return text;
}

export function formatKm(meters: number): string {
  const km = meters / 1000;
  const digits = Number.isInteger(km) ? 0 : 1;
  return `${new Intl.NumberFormat("ru-RU", { maximumFractionDigits: digits, minimumFractionDigits: digits }).format(km)} км`;
}

export function formatPct(value: number | null, digits = 1): string {
  if (value === null) return "—";
  return `${new Intl.NumberFormat("ru-RU", { maximumFractionDigits: digits, minimumFractionDigits: digits }).format(value)}%`;
}

export function formatShare(value: number | null): string {
  if (value === null) return "—";
  return formatPct(value * 100, 1);
}

export function formatMinute(planningStart: string, minute: number): string {
  const start = new Date(planningStart);
  const stamp = new Date(start.getTime() + minute * 60_000);
  return new Intl.DateTimeFormat("ru-RU", {
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
    timeZone: "Europe/Moscow",
  }).format(stamp);
}

export function formatWeight(kg: number): string {
  if (kg >= 1000 && kg % 100 === 0) {
    return `${new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 1 }).format(kg / 1000)} т`;
  }
  return `${new Intl.NumberFormat("ru-RU").format(kg)} кг`;
}

export function canonicalScenario(input: ScenarioInput): string {
  const scenario: Scenario = input.scenario;
  return JSON.stringify({
    dataset_id: input.dataset_id,
    dataset_version: input.dataset_version,
    objective: input.objective,
    scenario: {
      fuel_change_pct: scenario.fuel_change_pct,
      wage_change_pct: scenario.wage_change_pct,
      carrier_rate_change_pct: scenario.carrier_rate_change_pct,
      customer_rate_change_pct: scenario.customer_rate_change_pct,
      demand_change_pct: scenario.demand_change_pct,
      disabled_vehicle_ids: [...scenario.disabled_vehicle_ids].sort(),
      disabled_driver_ids: [...scenario.disabled_driver_ids].sort(),
      maintenance_remaining_overrides_m: Object.fromEntries(
        Object.entries(scenario.maintenance_remaining_overrides_m).sort(([a], [b]) => a.localeCompare(b)),
      ),
    },
  });
}

export function downloadJson(filename: string, data: unknown): void {
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}
