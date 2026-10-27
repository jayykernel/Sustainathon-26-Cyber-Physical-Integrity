"""Exercise a live WebSocket disconnect when the backend process is stopped."""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any

from websockets.exceptions import ConnectionClosed
from websockets.sync.client import connect


def _get_json(url: str, timeout: float = 5.0) -> dict[str, Any]:
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return json.load(response)


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]

    env = os.environ.copy()
    src_path = str(root / "backend" / "src")
    env["PYTHONPATH"] = os.pathsep.join(
        item for item in (src_path, env.get("PYTHONPATH", "")) if item
    )
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "physiguard.api.app:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        cwd=root,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        base_url = f"http://127.0.0.1:{port}"
        deadline = time.monotonic() + 15.0
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError(f"Backend exited before health check: {process.returncode}")
            try:
                health = _get_json(f"{base_url}/api/health", timeout=0.5)
                if health.get("status") == "ok" and health.get("thresholds_loaded") is True:
                    break
            except (OSError, ValueError):
                time.sleep(0.1)
        else:
            raise TimeoutError("Backend did not become healthy with calibrated thresholds")

        request = urllib.request.Request(
            f"{base_url}/api/sessions",
            data=json.dumps({"scenario_id": "baseline", "seed": 731, "speed": 1}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        session = _get_json_from_request(request)
        session_id = session.get("session_id")
        if not isinstance(session_id, str):
            raise RuntimeError("Backend did not return a session id")

        with connect(
            f"ws://127.0.0.1:{port}/api/sessions/{session_id}/ws",
            open_timeout=5,
        ) as socket_client:
            hello = json.loads(socket_client.recv(timeout=10))
            if hello.get("type") != "hello":
                raise RuntimeError(f"Expected WebSocket hello, received {hello.get('type')!r}")
            frame_batch = json.loads(socket_client.recv(timeout=10))
            if frame_batch.get("type") != "frame_batch":
                raise RuntimeError(
                    f"Expected first frame batch, received {frame_batch.get('type')!r}"
                )

            process.terminate()
            process.wait(timeout=5)
            close_deadline = time.monotonic() + 5.0
            while time.monotonic() < close_deadline:
                try:
                    socket_client.recv(timeout=max(0.1, close_deadline - time.monotonic()))
                except ConnectionClosed as exc:
                    print(f"PASS: backend termination closed the active stream (code {exc.code}).")
                    print("LIMIT: browser recovery and user-facing fallback require a browser walkthrough.")
                    return 0
            raise TimeoutError("WebSocket remained open after backend termination")
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)


def _get_json_from_request(request: urllib.request.Request) -> dict[str, Any]:
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.load(response)


if __name__ == "__main__":
    raise SystemExit(main())
