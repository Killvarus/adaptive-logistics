import hashlib
import json


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def canonical_hash(payload: object) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def scenario_payload(dataset_id: str, dataset_version: str, objective: str, scenario: object) -> dict:
    disabled_vehicles = sorted(scenario.disabled_vehicle_ids)
    disabled_drivers = sorted(scenario.disabled_driver_ids)
    overrides = {
        key: scenario.maintenance_remaining_overrides_m[key]
        for key in sorted(scenario.maintenance_remaining_overrides_m)
    }
    return {
        "dataset_id": dataset_id,
        "dataset_version": dataset_version,
        "objective": objective,
        "scenario": {
            "carrier_rate_change_pct": scenario.carrier_rate_change_pct,
            "customer_rate_change_pct": scenario.customer_rate_change_pct,
            "demand_change_pct": scenario.demand_change_pct,
            "disabled_driver_ids": disabled_drivers,
            "disabled_vehicle_ids": disabled_vehicles,
            "fuel_change_pct": scenario.fuel_change_pct,
            "maintenance_remaining_overrides_m": overrides,
            "wage_change_pct": scenario.wage_change_pct,
        },
    }
