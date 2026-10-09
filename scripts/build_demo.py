"""Собирает frontend в frontend/dist. FastAPI отдаёт этот каталог вместе с API."""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    required = [
        ROOT / "data" / "demo" / "regional_01.json",
        ROOT / "data" / "reference" / "tiny_economics_fixture.json",
        ROOT / "data" / "reference" / "tiny_economics_expected.json",
    ]
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        sys.exit("Нет файлов данных: " + ", ".join(missing))
    subprocess.check_call(["npm", "--prefix", str(ROOT / "frontend"), "run", "build"], cwd=ROOT)
    dist = ROOT / "frontend" / "dist" / "index.html"
    if not dist.is_file():
        sys.exit("Сборка frontend не создала dist/index.html")
    print(dist)


if __name__ == "__main__":
    main()
