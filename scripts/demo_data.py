"""Record deterministic P8 offline replay sessions for all seven scenarios."""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
from physiguard.api.app import create_app
from physiguard.attacks.scenarios import load_scenarios

PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = PROJECT_ROOT / "static-website" / "public" / "demo-runs"
DEMO_SEED = 4242


def record_scenario(scenario_id: str) -> tuple[str, int]:
    """Run one scenario at 60× and save the compact WebSocket frame stream."""
    with TestClient(create_app()) as client:
        response = client.post(
            "/api/sessions",
            json={"scenario_id": scenario_id, "seed": DEMO_SEED, "speed": 60},
        )
        response.raise_for_status()
        session_id = str(response.json()["session_id"])
        frames: list[dict[str, Any]] = []
        events: list[dict[str, Any]] = []
        with client.websocket_connect(f"/api/sessions/{session_id}/ws") as websocket:
            hello = websocket.receive_json()
            if hello.get("type") != "hello":
                raise RuntimeError(f"{scenario_id}: expected hello frame, got {hello!r}")
            while True:
                message = websocket.receive_json()
                message_type = message.get("type")
                if message_type == "frame_batch":
                    frames.extend(message["frames"])
                elif message_type == "event":
                    events.append(message)
                elif message_type == "done":
                    summary = message["summary"]
                    break
                elif message_type == "error":
                    raise RuntimeError(
                        f"{scenario_id}: server returned {message.get('code')}: "
                        f"{message.get('message')}"
                    )
                else:
                    raise RuntimeError(f"{scenario_id}: unknown server message {message!r}")
    if not frames or frames[0]["t"] != 0.0:
        raise RuntimeError(f"{scenario_id}: frame stream is empty or does not start at t=0")
    output = {
        "recorded_only": True,
        "scenario_id": scenario_id,
        "seed": DEMO_SEED,
        "config_hash": hello["config_hash"],
        "frame_count": len(frames),
        "events": events,
        "summary": summary,
        "frames": frames,
    }
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    target = OUTPUT_DIR / f"{scenario_id}.json"
    target.write_text(json.dumps(output, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    return scenario_id, len(frames)


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    scenario_ids = [item.id for item in load_scenarios().scenarios]
    with ThreadPoolExecutor(max_workers=4) as pool:
        for scenario_id, frame_count in pool.map(record_scenario, scenario_ids):
            print(f"recorded {scenario_id}: {frame_count} frames")


if __name__ == "__main__":
    main()
