"""Run the local API and Vite servers together, then stop both on exit."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"
BACKEND_URL = "http://127.0.0.1:8000/api/health"
FRONTEND_URL = "http://127.0.0.1:5173/"


def _http_ready(url: str) -> bool:
    try:
        with urlopen(url, timeout=0.5) as response:
            return response.status == 200
    except (OSError, URLError):
        return False


def _stop(processes: list[subprocess.Popen[bytes]]) -> None:
    for process in processes:
        if process.poll() is None:
            if os.name == "nt":
                subprocess.run(
                    ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                    check=False,
                    capture_output=True,
                )
            else:
                process.terminate()
    for process in processes:
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()


def main() -> int:
    """Start services, verify both local endpoints, and supervise until interrupted."""
    backend = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "physiguard.api.app:app", "--host", "127.0.0.1", "--port", "8000"],
        cwd=BACKEND,
    )
    processes = [backend]

    if os.name == "nt":
        npm = shutil.which("npm.cmd") or shutil.which("npm")
        if npm is None:
            _stop(processes)
            raise RuntimeError("npm was not found on PATH")
        frontend_command = f'"{npm}" run dev -- --host 127.0.0.1'
        frontend = subprocess.Popen(frontend_command, cwd=FRONTEND, shell=True)
    else:
        frontend = subprocess.Popen(
            ["npm", "run", "dev", "--", "--host", "127.0.0.1"], cwd=FRONTEND
        )
    processes.append(frontend)

    try:
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            if backend.poll() is not None or frontend.poll() is not None:
                raise RuntimeError("A development server exited during startup")
            if _http_ready(BACKEND_URL) and _http_ready(FRONTEND_URL):
                print("Backend at http://localhost:8000; frontend at http://localhost:5173")
                while backend.poll() is None and frontend.poll() is None:
                    time.sleep(0.25)
                raise RuntimeError("A development server stopped unexpectedly")
            time.sleep(0.25)
        raise RuntimeError("Development servers did not become ready within 20 seconds")
    except KeyboardInterrupt:
        return 0
    finally:
        _stop(processes)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as error:
        print(f"Development startup failed: {error}", file=sys.stderr)
        raise SystemExit(1) from error
