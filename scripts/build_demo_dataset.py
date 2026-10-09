"""Собирает стабильный синтетический набор data/demo/regional_01.json.

Генератор не вызывается на каждый HTTP-запрос. Результат — фиксированный JSON.
"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "demo" / "regional_01.json"

PROVENANCE = "synthetic_operations"
NETWORK = "demo_network"
TARIFFS = "demo_tariffs"


def _minutes(km: int) -> int:
    return max(18, int(round(km * 0.55)))


def edge(a, b, km, minutes, provenance=NETWORK):
    return {
        "id": f"{a}_{b}",
        "from_node_id": a,
        "to_node_id": b,
        "distance_m": km * 1000,
        "travel_time_min": minutes,
        "max_payload_kg": None,
        "allowed_body_types": [],
        "provenance_id": provenance,
    }


def order(oid, pickup, delivery, weight, body, sector, revenue, rank, outsourcing=False):
    return {
        "id": oid,
        "pickup_node_id": pickup,
        "delivery_node_id": delivery,
        "weight_kg": weight,
        "required_body_type": body,
        "sector_tag": sector,
        "pickup_earliest_min": 0,
        "pickup_latest_min": 540,
        "delivery_deadline_min": 600,
        "pickup_service_min": 15,
        "delivery_service_min": 15,
        "base_revenue_kopecks": revenue,
        "cancellation_compensation_kopecks": 0,
        "outsourcing_allowed": outsourcing,
        "demand_rank": rank,
        "provenance_id": PROVENANCE,
    }


def main() -> None:
    nodes = [
        ("MSK", "Москва · РЦ", "depot", 110, 70),
        ("POD", "Подольск · клиент", "customer", 300, 150),
        ("DOM", "Домодедово · клиент", "customer", 270, 320),
        ("CHE", "Чехов · хаб", "hub", 500, 190),
        ("SER", "Серпухов · клиент", "customer", 700, 90),
        ("OBN", "Обнинск · клиент", "customer", 730, 300),
    ]
    links = [
        ("MSK", "POD", 40),
        ("MSK", "DOM", 45),
        ("MSK", "CHE", 55),
        ("MSK", "SER", 70),
        ("MSK", "OBN", 85),
        ("POD", "DOM", 30),
        ("POD", "CHE", 35),
        ("DOM", "CHE", 32),
        ("CHE", "SER", 28),
        ("SER", "OBN", 36),
        ("CHE", "OBN", 48),
        ("DOM", "SER", 55),
        ("POD", "SER", 62),
        ("DOM", "OBN", 70),
        ("POD", "OBN", 78),
    ]
    edges = []
    for a, b, km in links:
        edges.append(edge(a, b, km, _minutes(km)))
        back_km = km + 15 if (a, b) == ("MSK", "OBN") else km
        edges.append(edge(b, a, back_km, _minutes(back_km) + (8 if back_km != km else 0)))

    orders = [
        order("O-01", "MSK", "POD", 4000, "tent", "retail", 1_800_000, 1),
        order("O-02", "POD", "MSK", 3200, "tent", "retail", 1_450_000, 2),
        order("O-03", "MSK", "DOM", 2800, "tent", "retail", 1_500_000, 3),
        order("O-04", "DOM", "MSK", 2400, "tent", "retail", 1_250_000, 4),
        order("O-05", "MSK", "CHE", 3600, "tent", "construction", 1_900_000, 5),
        order("O-06", "CHE", "MSK", 2200, "tent", "construction", 1_150_000, 6),
        order("O-07", "MSK", "SER", 7000, "tent", "construction", 2_600_000, 7, outsourcing=True),
        order("O-08", "POD", "DOM", 1500, "tent", "retail", 900_000, 8),
        order("O-09", "MSK", "POD", 1800, "refrigerated", "food", 2_100_000, 9),
        order("O-10", "POD", "MSK", 1600, "refrigerated", "food", 1_800_000, 10),
        order("O-11", "DOM", "CHE", 2000, "tent", "retail", 1_050_000, 11),
        order("O-12", "SER", "OBN", 2500, "tent", "construction", 1_400_000, 12, outsourcing=True),
        order("O-13", "MSK", "DOM", 2100, "tent", "retail", 1_000_000, 13),
        order("O-14", "CHE", "POD", 1800, "tent", "retail", 980_000, 14),
        order("O-15", "MSK", "POD", 2600, "tent", "retail", 1_200_000, 15),
        order("O-16", "OBN", "CHE", 1900, "tent", "construction", 1_100_000, 16),
    ]
    vehicles = [
        _vehicle("V-01", "Тент 12 т", "tent", 12000, "D-01", 2_000_000, 260, 320, 450, 350_000),
        _vehicle("V-02", "Тент 6 т", "tent", 6000, "D-02", 2_000_000, 240, 290, 400, 280_000),
        _vehicle("V-03", "Рефрижератор 8 т", "refrigerated", 8000, "D-03", 2_000_000, 280, 360, 520, 420_000),
        _vehicle("V-04", "Тент 20 т, малый остаток до ТО", "tent", 20000, "D-04", 120_000, 300, 380, 600, 500_000),
    ]
    drivers = [_driver(f"D-0{index}") for index in range(1, 5)]
    dataset = {
        "metadata": {
            "schema_version": "1.0",
            "dataset_id": "demo_ru_regional_01",
            "dataset_version": "1.0.0",
            "dataset_kind": "synthetic_demo",
            "seed": 20261009,
            "planning_start": "2026-10-09T08:00:00+03:00",
            "timezone": "Europe/Moscow",
            "horizon_min": 600,
            "currency": "RUB",
            "country_code": "RU",
            "disclaimer": "Условная российская сеть. Заказы, тарифы и расстояния синтетические.",
        },
        "base_active_count": 12,
        "base_parameters": {"fuel_price_kopecks_per_liter": 7000},
        "nodes": [
            {
                "id": item[0],
                "name": item[1],
                "kind": item[2],
                "ui_x": item[3],
                "ui_y": item[4],
                "country_code": "RU",
                "provenance_id": NETWORK,
            }
            for item in nodes
        ],
        "edges": edges,
        "order_pool": orders,
        "vehicles": vehicles,
        "drivers": drivers,
        "carriers": [
            {
                "id": "C-01",
                "name": "Условный подрядчик",
                "max_orders_per_horizon": 2,
                "provenance_id": TARIFFS,
            }
        ],
        "offers": [
            _offer("Q-07", "O-07", 3_200_000, 40, 420),
            _offer("Q-12", "O-12", 2_400_000, 80, 360),
        ],
        "provenance": [
            {
                "id": PROVENANCE,
                "title": "Заказы и парк",
                "kind": "synthetic_demo",
                "source_url": None,
                "country_code": "RU",
                "note": "Авторский демонстрационный набор, seed 20261009. Не история перевозчика.",
            },
            {
                "id": NETWORK,
                "title": "Схема дорог",
                "kind": "synthetic_demo",
                "source_url": None,
                "country_code": "RU",
                "note": "Условные длины и времена. Это не навигационная карта и не тариф платных дорог.",
            },
            {
                "id": TARIFFS,
                "title": "Тарифы и предложения подрядчиков",
                "kind": "synthetic_demo",
                "source_url": None,
                "country_code": "RU",
                "note": "Ставки заданы для демонстрации. Предложения не найдены на открытом рынке.",
            },
            {
                "id": "rosstat_not_imported",
                "title": "Российская статистика",
                "kind": "not_imported",
                "source_url": None,
                "country_code": "RU",
                "note": "Макроряд не импортирован. На тарифы модели не влияет.",
            },
            {
                "id": "company_not_connected",
                "title": "Данные компании",
                "kind": "not_connected",
                "source_url": None,
                "country_code": "RU",
                "note": "Выгрузка ERP/TMS не подключена.",
            },
        ],
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(dataset, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(OUT)


def _vehicle(vid, name, body, capacity, driver, maintenance_m, empty_ml, loaded_ml, wear, fixed):
    return {
        "id": vid,
        "name": name,
        "body_type": body,
        "capacity_kg": capacity,
        "home_node_id": "MSK",
        "assigned_driver_id": driver,
        "available_from_min": 0,
        "available_until_min": 600,
        "available": True,
        "maintenance_due_in_m": maintenance_m,
        "maintenance_buffer_m": 0,
        "fixed_cost_per_horizon_kopecks": fixed,
        "activation_cost_kopecks": 0,
        "wear_kopecks_per_km": wear,
        "fuel_empty_ml_per_km": empty_ml,
        "fuel_loaded_ml_per_km": loaded_ml,
        "provenance_id": PROVENANCE,
    }


def _driver(did):
    return {
        "id": did,
        "available": True,
        "available_from_min": 0,
        "available_until_min": 600,
        "max_driving_min": 600,
        "max_duty_min": 600,
        "fixed_wage_per_horizon_kopecks": 900_000,
        "variable_pay_per_hour_kopecks": 0,
        "provenance_id": PROVENANCE,
    }


def _offer(oid, order_id, price, pickup, delivery):
    return {
        "id": oid,
        "carrier_id": "C-01",
        "order_id": order_id,
        "base_price_kopecks": price,
        "planned_pickup_min": pickup,
        "planned_delivery_complete_min": delivery,
        "compatible": True,
        "valid_for_planning_start": "2026-10-09T08:00:00+03:00",
        "provenance_id": TARIFFS,
    }


if __name__ == "__main__":
    main()
