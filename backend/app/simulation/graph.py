import heapq
from collections import defaultdict

from app.domain.models import Edge


class PathResult:
    def __init__(self, edge_ids: tuple[str, ...], distance_m: int, travel_time_min: int) -> None:
        self.edge_ids = edge_ids
        self.distance_m = distance_m
        self.travel_time_min = travel_time_min


class RoadNetwork:
    """Физический граф. Вес поиска — distance_m; время берётся с того же пути."""

    def __init__(self, edges: list[Edge]) -> None:
        self._edges = list(edges)

    def shortest_path(
        self,
        source: str,
        target: str,
        *,
        load_kg: int,
        body_type: str,
    ) -> PathResult | None:
        if source == target:
            return PathResult((), 0, 0)
        adjacency: dict[str, list[Edge]] = defaultdict(list)
        for edge in self._edges:
            if edge.allowed_body_types and body_type not in edge.allowed_body_types:
                continue
            if load_kg > 0 and edge.max_payload_kg is not None and load_kg > edge.max_payload_kg:
                continue
            adjacency[edge.from_node_id].append(edge)
        for items in adjacency.values():
            items.sort(key=lambda edge: edge.id)

        best: dict[str, tuple[int, tuple[str, ...]]] = {source: (0, ())}
        times = {source: 0}
        heap: list[tuple[int, tuple[str, ...], str]] = [(0, (), source)]
        while heap:
            dist, edge_ids, node = heapq.heappop(heap)
            if best.get(node) != (dist, edge_ids):
                continue
            if node == target:
                return PathResult(edge_ids, dist, times[node])
            for edge in adjacency.get(node, ()):
                next_dist = dist + edge.distance_m
                next_ids = edge_ids + (edge.id,)
                key = (next_dist, next_ids)
                previous = best.get(edge.to_node_id)
                if previous is not None and previous <= key:
                    continue
                best[edge.to_node_id] = key
                times[edge.to_node_id] = times[node] + edge.travel_time_min
                heapq.heappush(heap, (next_dist, next_ids, edge.to_node_id))
        return None
