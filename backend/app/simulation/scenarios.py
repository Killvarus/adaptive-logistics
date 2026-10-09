from dataclasses import dataclass
from decimal import Decimal

from app.config import (
    CARRIER_PCT_RANGE,
    CUSTOMER_PCT_RANGE,
    DEMAND_PCT_RANGE,
    FUEL_PCT_RANGE,
    MAX_ACTIVE_ORDERS,
    MAX_VEHICLES,
    WAGE_PCT_RANGE,
)
from app.data.catalog import Catalog
from app.domain.models import Order, Scenario, ScenarioInput
from app.domain.money import round_half_up, scaled
from app.errors import ApiError


def requested_count(base_active_count: int, demand_change_pct: int) -> int:
    value = Decimal(base_active_count) * Decimal(100 + demand_change_pct) / Decimal(100)
    return round_half_up(value)


def select_active_orders(catalog: Catalog, demand_change_pct: int) -> list[Order]:
    count = requested_count(catalog.dataset.base_active_count, demand_change_pct)
    pool = catalog.dataset.order_pool
    if count < 0 or count > len(pool):
        raise ApiError(
            422,
            "INVALID_SCENARIO",
            "Пул заказов не покрывает запрошенное число заявок. Расчёт не обрезает спрос молча.",
            [{"path": "scenario.demand_change_pct", "message": "Пул не покрывает спрос"}],
        )
    ordered = sorted(pool, key=lambda order: (order.demand_rank, order.id))
    return ordered[:count]


@dataclass
class ScenarioSnapshot:
    catalog: Catalog
    scenario: Scenario
    active_orders: list[Order]
    fuel_price: Decimal
    disabled_vehicles: frozenset[str]
    disabled_drivers: frozenset[str]
    maintenance_overrides: dict[str, int]
    structural_change: bool

    def maintenance_due_m(self, vehicle_id: str, dataset_due_m: int) -> int:
        return self.maintenance_overrides.get(vehicle_id, dataset_due_m)


def zero_scenario(dataset_id: str, dataset_version: str) -> ScenarioInput:
    return ScenarioInput(
        dataset_id=dataset_id,
        dataset_version=dataset_version,
        scenario=Scenario(
            fuel_change_pct=0,
            wage_change_pct=0,
            carrier_rate_change_pct=0,
            customer_rate_change_pct=0,
            demand_change_pct=0,
            disabled_vehicle_ids=[],
            disabled_driver_ids=[],
            maintenance_remaining_overrides_m={},
        ),
    )


def build_snapshot(catalog: Catalog, scenario_input: ScenarioInput) -> ScenarioSnapshot:
    _validate_scenario(catalog, scenario_input)
    scenario = scenario_input.scenario
    active = select_active_orders(catalog, scenario.demand_change_pct)
    if len(active) > MAX_ACTIVE_ORDERS or len(catalog.dataset.vehicles) > MAX_VEHICLES:
        raise ApiError(
            422,
            "LIMIT_EXCEEDED",
            "В одном расчёте допускается не больше 24 активных заказов и 6 машин.",
        )
    structural = bool(
        scenario.demand_change_pct != 0
        or scenario.disabled_vehicle_ids
        or scenario.disabled_driver_ids
        or scenario.maintenance_remaining_overrides_m
    )
    return ScenarioSnapshot(
        catalog=catalog,
        scenario=scenario,
        active_orders=active,
        fuel_price=scaled(catalog.dataset.base_parameters.fuel_price_kopecks_per_liter, scenario.fuel_change_pct),
        disabled_vehicles=frozenset(scenario.disabled_vehicle_ids),
        disabled_drivers=frozenset(scenario.disabled_driver_ids),
        maintenance_overrides=dict(scenario.maintenance_remaining_overrides_m),
        structural_change=structural,
    )


def _validate_scenario(catalog: Catalog, scenario_input: ScenarioInput) -> None:
    dataset = catalog.dataset
    if scenario_input.dataset_version != dataset.metadata.dataset_version:
        raise ApiError(
            409,
            "DATASET_VERSION",
            "Версия набора данных не совпадает с загруженной.",
            [{"path": "dataset_version", "message": "Версия не совпадает"}],
        )
    scenario = scenario_input.scenario
    fields: list[dict[str, str]] = []
    ranges = {
        "fuel_change_pct": (*FUEL_PCT_RANGE, "Изменение стоимости топлива должно быть от −20 до +60%."),
        "wage_change_pct": (*WAGE_PCT_RANGE, "Изменение оплаты труда должно быть от 0 до +40%."),
        "carrier_rate_change_pct": (
            *CARRIER_PCT_RANGE,
            "Изменение ставки подрядчиков должно быть от −10 до +50%.",
        ),
        "customer_rate_change_pct": (
            *CUSTOMER_PCT_RANGE,
            "Изменение тарифа клиента должно быть от −20 до +10%.",
        ),
        "demand_change_pct": (
            *DEMAND_PCT_RANGE,
            "Изменение числа заказов должно быть от −30 до +30%.",
        ),
    }
    for name, (low, high, message) in ranges.items():
        value = getattr(scenario, name)
        if value < low or value > high:
            fields.append({"path": f"scenario.{name}", "message": message})
    vehicle_ids = set(catalog.vehicles)
    driver_ids = set(catalog.drivers)
    for vehicle_id in scenario.disabled_vehicle_ids:
        if vehicle_id not in vehicle_ids:
            fields.append(
                {"path": "scenario.disabled_vehicle_ids", "message": f"Неизвестная машина {vehicle_id}."}
            )
    for driver_id in scenario.disabled_driver_ids:
        if driver_id not in driver_ids:
            fields.append(
                {"path": "scenario.disabled_driver_ids", "message": f"Неизвестный водитель {driver_id}."}
            )
    for vehicle_id, remaining in scenario.maintenance_remaining_overrides_m.items():
        if vehicle_id not in vehicle_ids:
            fields.append(
                {
                    "path": "scenario.maintenance_remaining_overrides_m",
                    "message": f"Неизвестная машина {vehicle_id}.",
                }
            )
        elif remaining < 0:
            fields.append(
                {
                    "path": "scenario.maintenance_remaining_overrides_m",
                    "message": "Остаток пробега до ТО не может быть отрицательным.",
                }
            )
    if not fields:
        return
    message = fields[0]["message"] if len(fields) == 1 else "Проверьте параметры сценария."
    raise ApiError(422, "INVALID_SCENARIO", message, fields)
