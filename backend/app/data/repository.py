import json
import logging
from pathlib import Path

from app.config import DATA_DIR, DEMO_DATASET_ID
from app.data.catalog import Catalog
from app.domain.hashing import sha256_bytes
from app.domain.models import Dataset
from app.domain.validation import validate_dataset

logger = logging.getLogger(__name__)


class DatasetRepository:
    def __init__(self, data_dir: Path = DATA_DIR) -> None:
        self.data_dir = data_dir
        self.catalogs: dict[str, Catalog] = {}
        self.demo_valid = False
        self.demo_errors: list[str] = []

    def load(self) -> None:
        self.catalogs = {}
        self.demo_valid = False
        self.demo_errors = []
        paths = [
            self.data_dir / "demo" / "regional_01.json",
            self.data_dir / "reference" / "tiny_economics_fixture.json",
        ]
        benchmarks = self.data_dir / "benchmarks"
        if benchmarks.is_dir():
            paths.extend(sorted(benchmarks.glob("*.json")))
        for path in paths:
            if not path.is_file():
                if path.name == "regional_01.json":
                    self.demo_errors.append("Файл демонстрационного набора не найден.")
                continue
            catalog, errors = _read_catalog(path)
            if path.name == "regional_01.json":
                self.demo_errors = errors
                self.demo_valid = catalog is not None and catalog.dataset.metadata.dataset_id == DEMO_DATASET_ID
            if catalog is None:
                logger.error("Набор %s не прошёл проверку: %s", path.name, "; ".join(errors))
                continue
            self.catalogs[catalog.dataset.metadata.dataset_id] = catalog

    def get(self, dataset_id: str) -> Catalog | None:
        return self.catalogs.get(dataset_id)


_repository: DatasetRepository | None = None


def get_repository() -> DatasetRepository:
    global _repository
    if _repository is None:
        _repository = DatasetRepository()
        _repository.load()
    return _repository


def reload_repository() -> DatasetRepository:
    global _repository
    _repository = DatasetRepository()
    _repository.load()
    return _repository


def _read_catalog(path: Path) -> tuple[Catalog | None, list[str]]:
    raw = path.read_bytes()
    try:
        payload = json.loads(raw.decode("utf-8"))
        dataset = Dataset.model_validate(payload)
    except Exception as exc:
        return None, [f"Файл не соответствует схеме: {exc.__class__.__name__}."]
    errors = validate_dataset(dataset)
    if errors:
        return None, errors
    return Catalog.from_dataset(dataset, sha256_bytes(raw)), []
