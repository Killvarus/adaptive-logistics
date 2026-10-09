from app.domain.models import Dataset


def validate_dataset(dataset: Dataset) -> list[str]:
    errors: list[str] = []
    meta = dataset.metadata
    if meta.timezone != "Europe/Moscow":
        errors.append("Часовой пояс набора должен быть Europe/Moscow.")
    if dataset.base_active_count > len(dataset.order_pool):
        errors.append("base_active_count больше размера пула заказов.")

    def unique(label: str, ids: list[str]) -> None:
        if len(ids) != len(set(ids)):
            errors.append(f"Повторяющиеся идентификаторы: {label}.")
        if any(not item for item in ids):
            errors.append(f"Пустой идентификатор: {label}.")

    unique("nodes", [n.id for n in dataset.nodes])
    unique("edges", [e.id for e in dataset.edges])
    unique("orders", [o.id for o in dataset.order_pool])
    unique("vehicles", [v.id for v in dataset.vehicles])
    unique("drivers", [d.id for d in dataset.drivers])
    unique("carriers", [c.id for c in dataset.carriers])
    unique("offers", [o.id for o in dataset.offers])
    unique("provenance", [p.id for p in dataset.provenance])

    node_ids = {n.id for n in dataset.nodes}
    provenance_ids = {p.id for p in dataset.provenance}
    driver_ids = {d.id for d in dataset.drivers}
    order_ids = {o.id for o in dataset.order_pool}
    carrier_ids = {c.id for c in dataset.carriers}
    horizon = meta.horizon_min

    for node in dataset.nodes:
        _need_provenance(errors, provenance_ids, node.provenance_id, f"узел {node.id}")
    for edge in dataset.edges:
        if edge.from_node_id not in node_ids or edge.to_node_id not in node_ids:
            errors.append(f"Ребро {edge.id} ссылается на несуществующий узел.")
        if edge.max_payload_kg is not None and edge.max_payload_kg <= 0:
            errors.append(f"Ребро {edge.id}: ограничение массы должно быть положительным.")
        _need_provenance(errors, provenance_ids, edge.provenance_id, f"ребро {edge.id}")
    for order in dataset.order_pool:
        if order.pickup_node_id not in node_ids or order.delivery_node_id not in node_ids:
            errors.append(f"Заказ {order.id} ссылается на несуществующий узел.")
        if order.pickup_earliest_min > order.pickup_latest_min:
            errors.append(f"Заказ {order.id}: окно погрузки перевёрнуто.")
        if order.pickup_latest_min > horizon or order.delivery_deadline_min > horizon:
            errors.append(f"Заказ {order.id}: окно выходит за горизонт.")
        _need_provenance(errors, provenance_ids, order.provenance_id, f"заказ {order.id}")
    seen_drivers: set[str] = set()
    for vehicle in dataset.vehicles:
        if vehicle.home_node_id not in node_ids:
            errors.append(f"Машина {vehicle.id}: неизвестная база.")
        if vehicle.assigned_driver_id not in driver_ids:
            errors.append(f"Машина {vehicle.id}: неизвестный водитель.")
        elif vehicle.assigned_driver_id in seen_drivers:
            errors.append(f"Водитель {vehicle.assigned_driver_id} закреплён за двумя машинами.")
        else:
            seen_drivers.add(vehicle.assigned_driver_id)
        if vehicle.available_from_min > vehicle.available_until_min:
            errors.append(f"Машина {vehicle.id}: окно доступности перевёрнуто.")
        if vehicle.available_until_min > horizon:
            errors.append(f"Машина {vehicle.id}: доступность выходит за горизонт.")
        _need_provenance(errors, provenance_ids, vehicle.provenance_id, f"машина {vehicle.id}")
    for driver in dataset.drivers:
        if driver.available_from_min > driver.available_until_min:
            errors.append(f"Водитель {driver.id}: окно доступности перевёрнуто.")
        if driver.available_until_min > horizon:
            errors.append(f"Водитель {driver.id}: доступность выходит за горизонт.")
        _need_provenance(errors, provenance_ids, driver.provenance_id, f"водитель {driver.id}")
    for carrier in dataset.carriers:
        _need_provenance(errors, provenance_ids, carrier.provenance_id, f"подрядчик {carrier.id}")
    for offer in dataset.offers:
        if offer.carrier_id not in carrier_ids:
            errors.append(f"Предложение {offer.id}: неизвестный подрядчик.")
        if offer.order_id not in order_ids:
            errors.append(f"Предложение {offer.id}: неизвестный заказ.")
        if offer.planned_pickup_min > offer.planned_delivery_complete_min:
            errors.append(f"Предложение {offer.id}: время выполнения перевёрнуто.")
        _need_provenance(errors, provenance_ids, offer.provenance_id, f"предложение {offer.id}")
    return errors


def _need_provenance(errors: list[str], known: set[str], provenance_id: str, label: str) -> None:
    if provenance_id not in known:
        errors.append(f"{label}: неизвестное происхождение {provenance_id}.")
