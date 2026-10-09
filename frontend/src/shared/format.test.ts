import { describe, expect, it } from "vitest";
import { canonicalScenario, formatKm, formatRub, formatSignedRub } from "./format";
import { EMPTY_SCENARIO, type ScenarioInput } from "../api/types";

describe("format", () => {
  it("formats kopecks as rubles", () => {
    expect(formatRub(1_460_000)).toContain("14");
    expect(formatRub(1_460_000)).toContain("600");
    expect(formatSignedRub(-600_000)).toContain("6");
    expect(formatSignedRub(-600_000).startsWith("−") || formatSignedRub(-600_000).startsWith("-")).toBe(true);
  });

  it("formats kilometers from meters", () => {
    expect(formatKm(200_000)).toContain("200");
  });

  it("canonicalizes scenario lists", () => {
    const left: ScenarioInput = {
      dataset_id: "demo",
      dataset_version: "1.0.0",
      objective: "min_cost_with_full_service",
      scenario: { ...EMPTY_SCENARIO, disabled_vehicle_ids: ["V-02", "V-01"], fuel_change_pct: 25 },
    };
    const right: ScenarioInput = {
      ...left,
      scenario: { ...left.scenario, disabled_vehicle_ids: ["V-01", "V-02"] },
    };
    expect(canonicalScenario(left)).toBe(canonicalScenario(right));
  });
});
