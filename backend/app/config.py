from pathlib import Path

ENGINE_VERSION = "0.1.0"
SCHEMA_VERSION = "1.0"
MAX_ACTIVE_ORDERS = 24
MAX_VEHICLES = 6
MAX_CHAIN_LENGTH = 3
SOLVER_TIME_LIMIT_S = 5.0

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"
DEMO_DATASET_ID = "demo_ru_regional_01"

FUEL_PCT_RANGE = (-20, 60)
WAGE_PCT_RANGE = (0, 40)
CARRIER_PCT_RANGE = (-10, 50)
CUSTOMER_PCT_RANGE = (-20, 10)
DEMAND_PCT_RANGE = (-30, 30)

LEDGER_CATEGORIES = (
    "own_fuel",
    "own_wear",
    "driver_fixed_wage",
    "driver_variable_pay",
    "fleet_fixed_cost",
    "vehicle_activation",
    "outsourcing",
    "cancellation_compensation",
)

INPUT_BOUNDS = {
    "fuel_change_pct": {"min": -20, "max": 60, "step": 5},
    "wage_change_pct": {"min": 0, "max": 40, "step": 5},
    "carrier_rate_change_pct": {"min": -10, "max": 50, "step": 5},
    "customer_rate_change_pct": {"min": -20, "max": 10, "step": 5},
    "demand_change_pct": {"min": -30, "max": 30, "step": 5},
}
