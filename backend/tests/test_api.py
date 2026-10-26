"""Contract tests for the REST API and live session WebSocket."""

from __future__ import annotations

import asyncio
import math
import time
from typing import Any

import pytest
from fastapi.testclient import TestClient

from physiguard.api.app import create_app
from physiguard.api.sessions import SessionError, SessionManager
from physiguard.attacks.runner import run_paired_scenario as real_run_paired_scenario
from physiguard.config import Config, get_config


@pytest.fixture
def short_config(monkeypatch: pytest.MonkeyPatch) -> Config:
    config = get_config()
    monkeypatch.setattr("physiguard.api.sessions.get_config", lambda: config)

    def short_pair(
        attack_id: str,
        seed: int,
        config: Config,
        duration_s: int | None = None,
        attack_config_path: str | None = None,
    ) -> Any:
        del duration_s
        return real_run_paired_scenario(
            attack_id,
            seed,
            config,
            duration_s=45,
            attack_config_path=attack_config_path,
        )

    monkeypatch.setattr("physiguard.api.sessions.run_paired_scenario", short_pair)
    return config


def test_rest_contract_and_error_envelope(short_config: Config) -> None:
    app = create_app()
    with TestClient(app) as client:
        assert client.get("/api/health").json()["status"] == "ok"
        scenarios = client.get("/api/scenarios").json()
        assert {item["id"] for item in scenarios} == {
            "baseline",
            "spike",
            "drift",
            "replay",
            "model_synthesis",
            "malicious_command",
            "oracle_limit",
        }
        assert all(item["story_steps"] for item in scenarios)
        assert client.get("/api/limits").json()["limitations"]
        benchmarks = client.get("/api/benchmarks")
        assert benchmarks.status_code == 200
        assert set(benchmarks.json()) == {"results", "meta"}

        invalid = client.post("/api/sessions", json={"scenario_id": "bad", "speed": 2})
        assert invalid.status_code == 422
        assert set(invalid.json()) == {"error"}
        assert invalid.json()["error"]["code"] == "validation_error"

        unknown = client.get("/api/sessions/missing")
        assert unknown.status_code == 404
        assert unknown.json()["error"]["code"] == "session_error"


def test_cors_is_enabled_only_for_the_local_development_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PHYSIGUARD_DEV_CORS", "1")
    with TestClient(create_app()) as client:
        enabled = client.options(
            "/api/limits",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert enabled.headers["access-control-allow-origin"] == "http://localhost:5173"

    monkeypatch.delenv("PHYSIGUARD_DEV_CORS")
    with TestClient(create_app()) as client:
        disabled = client.get("/api/limits", headers={"Origin": "http://localhost:5173"})
        assert "access-control-allow-origin" not in disabled.headers


def test_websocket_errors_keep_connection_open_and_streams_frames(
    short_config: Config,
) -> None:
    app = create_app()
    with TestClient(app) as client:
        created = client.post(
            "/api/sessions", json={"scenario_id": "baseline", "seed": 7, "speed": 60}
        )
        assert created.status_code == 202
        session_id = created.json()["session_id"]
        with client.websocket_connect(f"/api/sessions/{session_id}/ws") as socket:
            assert socket.receive_json()["type"] == "hello"
            socket.send_text("not-json")
            socket.send_json({"type": "speed", "value": 3})
            socket.send_json({"type": "pause"})
            socket.send_json({"type": "resume"})
            messages: list[dict[str, Any]] = []
            while (
                not any(item["type"] == "frame_batch" for item in messages)
                or len([item for item in messages if item["type"] == "error"]) < 2
            ):
                messages.append(socket.receive_json())
            errors = [item for item in messages if item["type"] == "error"]
            assert all(item["code"] == "invalid_message" for item in errors)
            batch = next(item for item in messages if item["type"] == "frame_batch")
            assert 1 <= len(batch["frames"]) <= 10
            frame = batch["frames"][0]
            assert set(frame["truth"]) == {"soc", "v", "i", "temp"}
            assert set(frame["truth_undefended"]) == {"soc", "v", "i", "temp"}
            assert math.isfinite(frame["predicted"]["temp"])


def test_injection_repeats_for_same_seed_and_simulated_injection_time(
    short_config: Config,
) -> None:
    app = create_app()

    def run_injection(client: TestClient) -> list[dict[str, Any]]:
        created = client.post(
            "/api/sessions", json={"scenario_id": "baseline", "seed": 1234, "speed": 20}
        )
        session_id = created.json()["session_id"]
        with client.websocket_connect(f"/api/sessions/{session_id}/ws") as socket:
            assert socket.receive_json()["type"] == "hello"
            first_batch = socket.receive_json()
            assert first_batch["type"] == "frame_batch"
            socket.send_json({"type": "pause"})
            socket.send_json({"type": "inject", "attack": "AT1"})
            socket.send_json({"type": "resume"})
            for _ in range(12):
                message = socket.receive_json()
                if message["type"] == "frame_batch":
                    return message["frames"]
                if message["type"] == "error":
                    raise AssertionError(message)
        raise AssertionError("injected session did not resume")

    with TestClient(app) as client:
        first = run_injection(client)
        second = run_injection(client)
    assert first == second
    assert first[0]["attack"]["name"] == "spike"
    assert first[0]["attack"]["onset"] == 20


def test_four_session_limit_and_idle_expiration(
    short_config: Config, monkeypatch: pytest.MonkeyPatch
) -> None:
    app = create_app()

    async def hold(self: SessionManager, session: Any, attack_id: str | None) -> None:
        del self, attack_id
        session.status = "running"
        await asyncio.Event().wait()

    monkeypatch.setattr(SessionManager, "_run", hold)
    with TestClient(app) as client:
        ids = [
            client.post("/api/sessions", json={"scenario_id": "baseline"}).json()["session_id"]
            for _ in range(4)
        ]
        rejected = client.post("/api/sessions", json={"scenario_id": "baseline"})
        assert rejected.status_code == 429
        assert rejected.json()["error"]["code"] == "session_limit"
        manager = app.state.session_manager
        session = manager.get(ids[0])
        session.last_activity = time.monotonic() - 901
        with pytest.raises(SessionError, match="not found"):
            manager.get(ids[0])
        for session_id in ids[1:]:
            client.delete(f"/api/sessions/{session_id}")
