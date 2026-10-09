from dataclasses import dataclass
from decimal import Decimal

from app.domain.models import Driver, Leg, Offer, Vehicle
from app.domain.money import D, round_half_up, scaled, scaled_kopecks
from app.simulation.scenarios import ScenarioSnapshot
from app.simulation.schedule import Schedule


@dataclass(frozen=True)
class RouteCost:
    fuel: int
    wear: int
    variable_pay: int
    activation: int

    @property
    def variable_total(self) -> int:
        return self.fuel + self.wear + self.variable_pay + self.activation


def fuel_cost(legs: list[Leg], vehicle: Vehicle, fuel_price: Decimal) -> int:
    total = Decimal(0)
    for leg in legs:
        consumption = (
            vehicle.fuel_loaded_ml_per_km if leg.load_kg > 0 else vehicle.fuel_empty_ml_per_km
        )
        liters = D(leg.distance_m) * D(consumption) / D(1_000_000)
        total += liters * fuel_price
    return round_half_up(total)


def wear_cost(distance_m: int, vehicle: Vehicle) -> int:
    return round_half_up(D(distance_m) / D(1000) * D(vehicle.wear_kopecks_per_km))


def variable_pay(duty_min: int, driver: Driver, wage_change_pct: int) -> int:
    rate = scaled(driver.variable_pay_per_hour_kopecks, wage_change_pct)
    return round_half_up(D(duty_min) / D(60) * rate)


def fixed_wage(driver: Driver, wage_change_pct: int) -> int:
    return scaled_kopecks(driver.fixed_wage_per_horizon_kopecks, wage_change_pct)


def order_revenue(base_revenue_kopecks: int, customer_rate_change_pct: int) -> int:
    return scaled_kopecks(base_revenue_kopecks, customer_rate_change_pct)


def offer_price(offer: Offer, carrier_rate_change_pct: int) -> int:
    return scaled_kopecks(offer.base_price_kopecks, carrier_rate_change_pct)


def price_route(
    schedule: Schedule,
    vehicle: Vehicle,
    driver: Driver,
    snapshot: ScenarioSnapshot,
) -> RouteCost:
    return RouteCost(
        fuel=fuel_cost(schedule.legs, vehicle, snapshot.fuel_price),
        wear=wear_cost(schedule.distance_m, vehicle),
        variable_pay=variable_pay(schedule.duty_min, driver, snapshot.scenario.wage_change_pct),
        activation=vehicle.activation_cost_kopecks,
    )
