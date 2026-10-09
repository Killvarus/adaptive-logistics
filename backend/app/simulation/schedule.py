from dataclasses import dataclass, field

from app.domain.models import Driver, Leg, Order, RouteEvent, RoutingPolicy, Vehicle
from app.simulation.graph import RoadNetwork


@dataclass
class Schedule:
    legs: list[Leg]
    events: list[RouteEvent]
    start_min: int
    finish_min: int
    duty_min: int
    driving_min: int
    distance_m: int
    empty_distance_m: int
    loaded_distance_m: int
    maintenance_slack_m: int
    delivery_slack_min: dict[str, int]


@dataclass
class ScheduleFailure:
    code: str
    message: str
    distance_m: int = 0


@dataclass
class _Build:
    legs: list[Leg] = field(default_factory=list)
    events: list[RouteEvent] = field(default_factory=list)
    node: str = ""
    time: int = 0
    load_kg: int = 0
    duty_start: int | None = None
    driving_min: int = 0
    delivery_slack_min: dict[str, int] = field(default_factory=dict)

    def touch(self, moment: int) -> None:
        if self.duty_start is None:
            self.duty_start = moment


def simulate_route(
    network: RoadNetwork,
    vehicle: Vehicle,
    driver: Driver,
    orders: list[Order],
    *,
    policy: RoutingPolicy,
    maintenance_due_m: int,
) -> Schedule | ScheduleFailure:
    if not orders:
        return ScheduleFailure("empty", "Пустая последовательность заказов.")
    if not vehicle.available:
        return ScheduleFailure("vehicle_unavailable", "Машина недоступна.")
    if not driver.available:
        return ScheduleFailure("driver_unavailable", "Водитель недоступен.")

    state = _Build(
        node=vehicle.home_node_id,
        time=max(vehicle.available_from_min, driver.available_from_min),
    )
    home = vehicle.home_node_id

    for index, order in enumerate(orders):
        if vehicle.body_type != order.required_body_type:
            return ScheduleFailure("body", "Тип кузова не подходит заказу.")
        if order.weight_kg > vehicle.capacity_kg:
            return ScheduleFailure("capacity", "Масса заказа больше грузоподъёмности.")
        if state.load_kg != 0:
            return ScheduleFailure("capacity", "В кузове остался предыдущий груз.")
        if policy == "return_between_orders" and index > 0:
            moved = _travel(network, state, vehicle, home, 0, None, "empty")
            if isinstance(moved, ScheduleFailure):
                return moved
        moved = _travel(network, state, vehicle, order.pickup_node_id, 0, None, "empty")
        if isinstance(moved, ScheduleFailure):
            return moved
        if state.time < order.pickup_earliest_min:
            state.touch(state.time)
            state.events.append(
                RouteEvent(
                    type="wait",
                    node_id=state.node,
                    start_min=state.time,
                    finish_min=order.pickup_earliest_min,
                    order_id=order.id,
                    load_before_kg=0,
                    load_after_kg=0,
                )
            )
            state.time = order.pickup_earliest_min
        if state.time > order.pickup_latest_min:
            return ScheduleFailure("pickup_window", "Погрузка начинается позже окна.")
        state.touch(state.time)
        pickup_finish = state.time + order.pickup_service_min
        state.events.append(
            RouteEvent(
                type="pickup",
                node_id=state.node,
                start_min=state.time,
                finish_min=pickup_finish,
                order_id=order.id,
                load_before_kg=0,
                load_after_kg=order.weight_kg,
            )
        )
        state.time = pickup_finish
        state.load_kg = order.weight_kg
        moved = _travel(
            network,
            state,
            vehicle,
            order.delivery_node_id,
            order.weight_kg,
            order.id,
            "loaded",
        )
        if isinstance(moved, ScheduleFailure):
            return moved
        delivery_finish = state.time + order.delivery_service_min
        if delivery_finish > order.delivery_deadline_min:
            return ScheduleFailure(
                "delivery_deadline",
                "Разгрузка завершается позже срока заказа.",
            )
        state.touch(state.time)
        state.events.append(
            RouteEvent(
                type="delivery",
                node_id=state.node,
                start_min=state.time,
                finish_min=delivery_finish,
                order_id=order.id,
                load_before_kg=order.weight_kg,
                load_after_kg=0,
            )
        )
        state.delivery_slack_min[order.id] = order.delivery_deadline_min - delivery_finish
        state.time = delivery_finish
        state.load_kg = 0

    moved = _travel(network, state, vehicle, home, 0, None, "empty")
    if isinstance(moved, ScheduleFailure):
        return moved

    if state.duty_start is None:
        return ScheduleFailure("shift", "Маршрут не содержит рабочего времени.")
    finish = state.time
    duty = finish - state.duty_start
    window_end = min(vehicle.available_until_min, driver.available_until_min)
    if finish > window_end or state.duty_start < max(
        vehicle.available_from_min, driver.available_from_min
    ):
        return ScheduleFailure("shift", "Маршрут выходит за окно смены.")
    if duty > driver.max_duty_min:
        return ScheduleFailure("duty", "Время работы водителя больше заданного лимита.")
    if state.driving_min > driver.max_driving_min:
        return ScheduleFailure("driving", "Время вождения больше заданного лимита.")

    distance = sum(leg.distance_m for leg in state.legs)
    slack = maintenance_due_m - vehicle.maintenance_buffer_m - distance
    if slack < 0:
        return ScheduleFailure(
            "maintenance",
            "Пробег с возвратом больше остатка до ТО.",
            distance_m=distance,
        )
    empty = sum(leg.distance_m for leg in state.legs if leg.kind == "empty")
    loaded = sum(leg.distance_m for leg in state.legs if leg.kind == "loaded")
    return Schedule(
        legs=state.legs,
        events=state.events,
        start_min=state.duty_start,
        finish_min=finish,
        duty_min=duty,
        driving_min=state.driving_min,
        distance_m=distance,
        empty_distance_m=empty,
        loaded_distance_m=loaded,
        maintenance_slack_m=slack,
        delivery_slack_min=state.delivery_slack_min,
    )


def _travel(
    network: RoadNetwork,
    state: _Build,
    vehicle: Vehicle,
    target: str,
    load_kg: int,
    order_id: str | None,
    kind: str,
) -> ScheduleFailure | None:
    path = network.shortest_path(
        state.node,
        target,
        load_kg=load_kg,
        body_type=vehicle.body_type,
    )
    if path is None:
        return ScheduleFailure("unreachable", "Нет допустимого пути между точками.")
    if path.distance_m == 0:
        state.node = target
        return None
    depart = state.time
    arrive = state.time + path.travel_time_min
    state.touch(depart)
    state.legs.append(
        Leg(
            from_node_id=state.node,
            to_node_id=target,
            path_edge_ids=list(path.edge_ids),
            depart_min=depart,
            arrive_min=arrive,
            distance_m=path.distance_m,
            load_kg=load_kg,
            order_id=order_id,
            kind=kind,  # type: ignore[arg-type]
        )
    )
    state.driving_min += path.travel_time_min
    state.time = arrive
    state.node = target
    return None
