from dataclasses import dataclass

from app.domain.models import Carrier, Dataset, Driver, Node, Offer, Order, Vehicle
from app.simulation.graph import RoadNetwork


@dataclass
class Catalog:
    dataset: Dataset
    dataset_hash: str
    nodes: dict[str, Node]
    orders: dict[str, Order]
    vehicles: dict[str, Vehicle]
    drivers: dict[str, Driver]
    carriers: dict[str, Carrier]
    offers: dict[str, Offer]
    network: RoadNetwork

    @classmethod
    def from_dataset(cls, dataset: Dataset, dataset_hash: str) -> "Catalog":
        return cls(
            dataset=dataset,
            dataset_hash=dataset_hash,
            nodes={item.id: item for item in dataset.nodes},
            orders={item.id: item for item in dataset.order_pool},
            vehicles={item.id: item for item in dataset.vehicles},
            drivers={item.id: item for item in dataset.drivers},
            carriers={item.id: item for item in dataset.carriers},
            offers={item.id: item for item in dataset.offers},
            network=RoadNetwork(dataset.edges),
        )
