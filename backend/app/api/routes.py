import itertools
import logging
import threading
from contextlib import contextmanager

from fastapi import APIRouter

from app.config import DEMO_DATASET_ID, ENGINE_VERSION, INPUT_BOUNDS
from app.data.catalog import Catalog
from app.data.repository import get_repository
from app.domain.models import ScenarioInput
from app.errors import ApiError
from app.planning.orchestrator import evaluate, optimize, ortools_available
from app.simulation.scenarios import select_active_orders

logger = logging.getLogger(__name__)
router = APIRouter()
_lock = threading.Lock()
_request_ids = itertools.count(1)


def next_request_id() -> str:
    return f"local-request-{next(_request_ids)}"


@contextmanager
def compute_slot():
    if not _lock.acquire(blocking=False):
        raise ApiError(
            409,
            "BUSY",
            "Уже выполняется расчёт. Повторите запрос после его завершения.",
        )
    try:
        yield
    finally:
        _lock.release()


@router.get("/health")
def health() -> dict:
    repository = get_repository()
    demo = repository.get(DEMO_DATASET_ID)
    loaded = repository.demo_valid and demo is not None
    return {
        "status": "ok" if loaded else "error",
        "engine_version": ENGINE_VERSION,
        "demo_dataset_loaded": loaded,
        "solver_available": ortools_available(),
    }


@router.get("/datasets/demo")
def demo_dataset() -> dict:
    catalog = get_repository().get(DEMO_DATASET_ID)
    if catalog is None:
        raise ApiError(404, "DATASET_NOT_FOUND", "Демонстрационный набор не загружен.")
    active = select_active_orders(catalog, 0)
    return {
        "dataset": catalog.dataset.model_dump(mode="json"),
        "dataset_hash": catalog.dataset_hash,
        "active_order_ids": [order.id for order in active],
        "input_bounds": INPUT_BOUNDS,
    }


@router.post("/evaluate")
def post_evaluate(payload: ScenarioInput):
    with compute_slot():
        return evaluate(_require_catalog(payload.dataset_id), payload)


@router.post("/optimize")
def post_optimize(payload: ScenarioInput):
    with compute_slot():
        return optimize(_require_catalog(payload.dataset_id), payload)


def _require_catalog(dataset_id: str) -> Catalog:
    if "/" in dataset_id or "\\" in dataset_id or ".." in dataset_id:
        raise ApiError(
            422,
            "INVALID_SCENARIO",
            "Идентификатор набора данных не может быть путём к файлу.",
            [{"path": "dataset_id", "message": "Ожидается идентификатор, не путь"}],
        )
    catalog = get_repository().get(dataset_id)
    if catalog is None:
        raise ApiError(404, "DATASET_NOT_FOUND", "Неизвестный набор данных.")
    return catalog
