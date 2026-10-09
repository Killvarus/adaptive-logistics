import json

import pytest

from app.config import ROOT
from app.data.catalog import Catalog
from app.domain.hashing import sha256_bytes
from app.domain.models import Dataset, Scenario, ScenarioInput
from app.domain.validation import validate_dataset

FIXTURE = ROOT / "data" / "reference" / "tiny_economics_fixture.json"
EXPECTED = ROOT / "data" / "reference" / "tiny_economics_expected.json"


@pytest.fixture(scope="session")
def tiny_catalog() -> Catalog:
    raw = FIXTURE.read_bytes()
    dataset = Dataset.model_validate(json.loads(raw.decode("utf-8")))
    errors = validate_dataset(dataset)
    assert errors == []
    return Catalog.from_dataset(dataset, sha256_bytes(raw))


@pytest.fixture(scope="session")
def expected() -> dict:
    return json.loads(EXPECTED.read_text(encoding="utf-8"))


def scenario_input(dataset: Dataset, **overrides) -> ScenarioInput:
    values = {
        "fuel_change_pct": 0,
        "wage_change_pct": 0,
        "carrier_rate_change_pct": 0,
        "customer_rate_change_pct": 0,
        "demand_change_pct": 0,
        "disabled_vehicle_ids": [],
        "disabled_driver_ids": [],
        "maintenance_remaining_overrides_m": {},
    }
    values.update(overrides)
    return ScenarioInput(
        dataset_id=dataset.metadata.dataset_id,
        dataset_version=dataset.metadata.dataset_version,
        scenario=Scenario(**values),
    )


def reference_input(dataset: Dataset) -> ScenarioInput:
    return scenario_input(dataset, fuel_change_pct=25, wage_change_pct=10)
