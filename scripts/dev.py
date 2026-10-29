"""Run the local API and Vite servers together, then stop both on exit."""

from __future__ import annotations

import argparse
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
FRONTEND = ROOT / "static-website"
BACKEND_URL = "http://127.0.0.1:8000/api/health"
FRONTEND_URL = "http://127.0.0.1:4173/"
PACKAGE_MANAGERS = ("auto", "bun", "npm")


def _http_ready(url: str) -> bool:
    try:
        with urlopen(url, timeout=0.5) as response:
            return response.status == 200
    except (OSError, URLError):
        return False


def _find_package_manager(name: str) -> str | None:
    """Return the executable path for ``bun`` or ``npm`` (npm.cmd on Windows)."""
    if name == "bun":
        return shutil.which("bun")
    return shutil.which("npm.cmd") or shutil.which("npm")


def _resolve_package_manager(requested: str) -> str:
    """Resolve ``auto``/``bun``/``npm`` to an available package manager name."""
    if requested != "auto":
        if _find_package_manager(requested) is None:
            raise RuntimeError(f"{requested} was not found on PATH")
        return requested
    if _find_package_manager("bun") is not None:
        return "bun"
    if _find_package_manager("npm") is not None:
        return "npm"
    raise RuntimeError("Neither bun nor npm was found on PATH")


def _frontend_command(package_manager: str) -> tuple[list[str] | str, bool]:
    """Build the Vite dev command for the selected package manager.

    Returns the command and whether it must run through a shell (Windows npm).
    """
    executable = _find_package_manager(package_manager)
    if executable is None:
        raise RuntimeError(f"{package_manager} was not found on PATH")
    if package_manager == "npm" and os.name == "nt":
        return f'"{executable}" run dev -- --host 127.0.0.1', True
    return [executable, "run", "dev", "--", "--host", "127.0.0.1"], False


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


def main(argv: list[str] | None = None) -> int:
    """Start services, verify both local endpoints, and supervise until interrupted."""
    env_pm = os.environ.get("PHYSIGUARD_JS_PM")
    default_pm = env_pm if env_pm in PACKAGE_MANAGERS else "auto"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--pm",
        choices=PACKAGE_MANAGERS,
        default=default_pm,
        help="Frontend package manager: auto (bun, then npm), bun, or npm.",
    )
    args = parser.parse_args(argv)
    package_manager = _resolve_package_manager(args.pm)

    environment = os.environ.copy()
    environment["PHYSIGUARD_DEV_CORS"] = "1"
    backend = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "physiguard.api.app:app", "--host", "127.0.0.1", "--port", "8000"],
        cwd=BACKEND,
        env=environment,
    )
    processes = [backend]

    try:
        frontend_command, frontend_shell = _frontend_command(package_manager)
    except RuntimeError:
        _stop(processes)
        raise
    frontend = subprocess.Popen(frontend_command, cwd=FRONTEND, shell=frontend_shell)
    processes.append(frontend)

    try:
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            if backend.poll() is not None or frontend.poll() is not None:
                raise RuntimeError("A development server exited during startup")
            if _http_ready(BACKEND_URL) and _http_ready(FRONTEND_URL):
                print(
                    "Backend API at http://localhost:8000; "
                    f"PhysiGuard live interface at http://localhost:4173 (frontend: {package_manager})"
                )
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
