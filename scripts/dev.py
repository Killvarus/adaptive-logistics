"""Запускает API и Vite. Ctrl+C останавливает оба процесса."""

import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    backend = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app.main:app",
            "--app-dir",
            str(ROOT / "backend"),
            "--host",
            "127.0.0.1",
            "--port",
            "8000",
        ],
        cwd=ROOT,
    )
    frontend = subprocess.Popen(["npm", "--prefix", str(ROOT / "frontend"), "run", "dev"], cwd=ROOT)
    print("API http://127.0.0.1:8000")
    print("UI  http://127.0.0.1:5173")
    try:
        while backend.poll() is None and frontend.poll() is None:
            time.sleep(0.4)
    except KeyboardInterrupt:
        pass
    finally:
        for process in (frontend, backend):
            if process.poll() is None:
                process.terminate()
        for process in (frontend, backend):
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()


if __name__ == "__main__":
    main()
