from dataclasses import dataclass

from app.domain.models import RoutingPolicy
from app.simulation.schedule import Schedule


@dataclass
class OwnRoute:
    vehicle_id: str
    driver_id: str
    policy: RoutingPolicy
    order_ids: list[str]
    schedule: Schedule
    fuel_kopecks: int
    wear_kopecks: int
    variable_pay_kopecks: int
    activation_kopecks: int
    variable_cost_kopecks: int


@dataclass
class OutAssignment:
    offer_id: str
    carrier_id: str
    order_id: str


@dataclass
class Unserved:
    order_id: str
    reason_code: str
    message: str


@dataclass
class Assignment:
    routes: list[OwnRoute]
    outsourced: list[OutAssignment]
    unserved: list[Unserved]


@dataclass(frozen=True)
class PricedOffer:
    offer_id: str
    carrier_id: str
    order_id: str
    price_kopecks: int
    planned_pickup_min: int
    planned_delivery_complete_min: int
