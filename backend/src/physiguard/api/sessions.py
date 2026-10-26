"""Deterministic simulation sessions and their WebSocket playback protocol."""

from __future__ import annotations

import asyncio
import json
import math
import tempfile
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import yaml
from fastapi import WebSocket, WebSocketDisconnect
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from physiguard.attacks.base import load_attack_definitions
from physiguard.attacks.runner import AttackTrajectory, run_paired_scenario
from physiguard.attacks.scenarios import load_scenarios
from physiguard.config import CONFIG_DIR, get_config
from physiguard.localize import LocalizationEngine, load_localization_config

ALLOWED_SPEEDS = {1, 5, 20, 60}
MAX_SESSIONS = 4
IDLE_TIMEOUT_S = 15 * 60
ATTACK_NAMES = {key: value.name for key, value in load_attack_definitions()[1].items()}


class CreateSessionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scenario_id: str = Field(min_length=1)
    seed: int = Field(default=4242, ge=0, le=2**32 - 1)
    speed: Literal[1, 5, 20, 60] = 1


class ClientMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["inject", "pause", "resume", "speed", "reset", "operator_reset"]
    attack: str | None = None
    params: dict[str, float | int] | None = None
    value: int | None = None
    seed: int | None = Field(default=None, ge=0, le=2**32 - 1)


@dataclass
class SimulationSession:
    session_id: str
    scenario_id: str
    attack_id: str | None
    seed: int
    speed: int
    status: str = "queued"
    created_at: float = field(default_factory=time.monotonic)
    last_activity: float = field(default_factory=time.monotonic)
    undefended: AttackTrajectory | None = None
    defended: AttackTrajectory | None = None
    localized: list[dict[str, Any]] | None = None
    replacement_undefended: AttackTrajectory | None = None
    replacement_defended: AttackTrajectory | None = None
    replacement_localized: list[dict[str, Any]] | None = None
    replacement_from: int | None = None
    attack_config_override: dict[str, Any] | None = None
    cursor: int = 0
    paused: bool = False
    error: str | None = None
    task: asyncio.Task[None] | None = None
    events_sent: set[tuple[float, str]] = field(default_factory=set)

    @property
    def total_steps(self) -> int:
        if self.defended is None:
            return 0
        return len(self.defended["t"])


class SessionError(ValueError):
    """A session or WebSocket command could not be applied."""

    code = "session_error"


class SessionLimitError(SessionError):
    """The server already has its maximum number of active sessions."""

    code = "session_limit"


class SessionManager:
    """Own, run, expire, and stream a bounded set of deterministic sessions."""

    def __init__(self) -> None:
        self.sessions: dict[str, SimulationSession] = {}
        self._lock = asyncio.Lock()

    async def create(self, request: CreateSessionRequest) -> SimulationSession:
        catalog = load_scenarios()
        scenario = next(
            (item for item in catalog.scenarios if item.id == request.scenario_id), None
        )
        if scenario is None:
            raise SessionError(f"Unknown scenario_id: {request.scenario_id}")
        async with self._lock:
            self.cleanup_idle()
            active = [
                item
                for item in self.sessions.values()
                if item.status in {"queued", "running", "ready", "paused"}
            ]
            if len(active) >= MAX_SESSIONS:
                raise SessionLimitError(
                    "Four sessions are already active; finish or delete one first."
                )
            session = SimulationSession(
                session_id=uuid.uuid4().hex,
                scenario_id=request.scenario_id,
                attack_id=scenario.attack,
                seed=request.seed,
                speed=request.speed,
            )
            self.sessions[session.session_id] = session
            session.task = asyncio.create_task(self._run(session, scenario.attack))
            logger_info(
                "session_created", session_id=session.session_id, scenario=request.scenario_id
            )
            return session

    async def _run(
        self,
        session: SimulationSession,
        attack_id: str | None,
        attack_config_path: str | None = None,
    ) -> None:
        session.status = "running"
        try:
            pair = await asyncio.to_thread(
                run_paired_scenario,
                attack_id or "baseline",
                session.seed,
                get_config(),
                None,
                attack_config_path,
            )
            session.undefended, session.defended = pair
            session.localized = await asyncio.to_thread(
                _localize_trace, session.defended, attack_id or "baseline"
            )
            session.status = "ready"
        except Exception as exc:
            session.status = "failed"
            session.error = "Simulation failed; see server logs for the session id."
            logger_error("session_failed", session_id=session.session_id, error=repr(exc))
            raise
        finally:
            session.last_activity = time.monotonic()

    def get(self, session_id: str) -> SimulationSession:
        self.cleanup_idle()
        session = self.sessions.get(session_id)
        if session is None:
            raise SessionError(f"Session not found: {session_id}")
        session.last_activity = time.monotonic()
        return session

    def delete(self, session_id: str) -> bool:
        session = self.sessions.pop(session_id, None)
        if session is None:
            return False
        if session.task is not None and not session.task.done():
            session.task.cancel()
        logger_info("session_deleted", session_id=session_id)
        return True

    def cleanup_idle(self) -> None:
        now = time.monotonic()
        for session_id, session in list(self.sessions.items()):
            if now - session.last_activity > IDLE_TIMEOUT_S:
                self.delete(session_id)

    def close(self) -> None:
        """Cancel remaining session tasks during application shutdown."""
        for session_id in list(self.sessions):
            self.delete(session_id)

    def status(self, session: SimulationSession) -> dict[str, Any]:
        return {
            "session_id": session.session_id,
            "scenario_id": session.scenario_id,
            "seed": session.seed,
            "status": "paused" if session.paused else session.status,
            "speed": session.speed,
            "current_step": session.cursor,
            "total_steps": session.total_steps,
            "error": session.error,
        }

    async def inject(
        self, session: SimulationSession, attack_id: str, params: dict[str, float | int]
    ) -> None:
        if attack_id not in {f"AT{index}" for index in range(1, 7)}:
            raise SessionError("attack must be one of AT1 through AT6")
        if session.defended is None or session.undefended is None:
            raise SessionError("Simulation is not ready for injection")
        if session.cursor >= session.total_steps:
            raise SessionError("Cannot inject after the simulation has completed")
        raw = yaml.safe_load((CONFIG_DIR / "attacks.yaml").read_text(encoding="utf-8"))
        attack = raw["attacks"][attack_id]
        unknown = set(params) - set(attack["parameters"])
        if unknown:
            raise SessionError(f"Unknown parameters for {attack_id}: {', '.join(sorted(unknown))}")
        if any(not math.isfinite(float(value)) for value in params.values()):
            raise SessionError("Attack parameters must be finite numbers")
        attack["parameters"].update(params)
        dt = float(get_config().simulation.dt)
        onset = int(round(float(session.defended["t"][session.cursor]) / dt))
        raw["onset_range_s"] = [onset, onset]
        attack["onset_s"] = onset
        with tempfile.TemporaryDirectory(prefix="physiguard-inject-") as temp_dir:
            path = Path(temp_dir) / "attacks.yaml"
            path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
            undefended, defended = await asyncio.to_thread(
                run_paired_scenario,
                attack_id,
                session.seed,
                get_config(),
                None,
                str(path),
            )
        localized = await asyncio.to_thread(_localize_trace, defended, attack_id)
        session.replacement_undefended = undefended
        session.replacement_defended = defended
        session.replacement_localized = localized
        session.replacement_from = session.cursor
        session.attack_id = attack_id
        session.attack_config_override = raw
        session.last_activity = time.monotonic()
        logger_info(
            "attack_injected", session_id=session.session_id, attack=attack_id, onset_s=onset
        )

    async def request_operator_reset(
        self, session: SimulationSession
    ) -> tuple[bool, bool, str | None]:
        """Replay deterministically with an operator reset at the current SAFE_MODE time."""
        if session.defended is None or session.cursor >= session.total_steps:
            return False, False, "Session has no active simulation step."
        if str(session.defended["response_state"][session.cursor]) != "SAFE_MODE":
            return False, False, "Operator reset is only available in SAFE_MODE."
        attack_id = session.attack_id or "baseline"
        reset_time = float(session.defended["t"][session.cursor])
        if session.attack_config_override is None:
            undefended, defended = await asyncio.to_thread(
                run_paired_scenario,
                attack_id,
                session.seed,
                get_config(),
                None,
                None,
                reset_time,
            )
        else:
            with tempfile.TemporaryDirectory(prefix="physiguard-reset-") as temp_dir:
                path = Path(temp_dir) / "attacks.yaml"
                path.write_text(
                    yaml.safe_dump(session.attack_config_override, sort_keys=False),
                    encoding="utf-8",
                )
                undefended, defended = await asyncio.to_thread(
                    run_paired_scenario,
                    attack_id,
                    session.seed,
                    get_config(),
                    None,
                    str(path),
                    reset_time,
                )
        localized = await asyncio.to_thread(_localize_trace, defended, attack_id)
        session.replacement_undefended = undefended
        session.replacement_defended = defended
        session.replacement_localized = localized
        session.replacement_from = session.cursor
        completed = any(event["code"] == "operator_reset" for event in defended["events"])
        session.last_activity = time.monotonic()
        logger_info(
            "operator_reset_requested",
            session_id=session.session_id,
            time_s=reset_time,
            reset_completed=completed,
        )
        return True, completed, None

    def frame(self, session: SimulationSession, index: int) -> dict[str, Any]:
        if session.defended is None or session.undefended is None:
            raise SessionError("Simulation is not ready")
        defended, undefended = session.defended, session.undefended
        localized = session.localized
        if session.replacement_from is not None and index >= session.replacement_from:
            assert session.replacement_defended is not None
            assert session.replacement_undefended is not None
            defended, undefended = session.replacement_defended, session.replacement_undefended
            localized = session.replacement_localized
        config = get_config()
        t_s = float(defended["t"][index])
        reported_v, reported_i, reported_t = (
            float(defended[key][index]) for key in ("V_rep", "I_rep", "T_rep")
        )
        estimated_v = float(defended["estimate_voltage"][index])
        estimated_t = float(defended["estimate_temperature"][index])
        estimated_soc = float(defended["estimate_soc"][index])
        attack_active = bool(defended["attack_active"][index])
        onset = defended["attack_onset_s"]
        attack_name = ATTACK_NAMES.get(session.attack_id or "", "baseline")
        return {
            "t": t_s,
            "truth": {
                "soc": float(defended["soc_true"][index]),
                "v": float(defended["V_true"][index]),
                "i": float(defended["I_cmd"][index]),
                "temp": float(defended["T_true"][index]),
            },
            "truth_undefended": {
                "soc": float(undefended["soc_true"][index]),
                "v": float(undefended["V_true"][index]),
                "i": float(undefended["I_cmd"][index]),
                "temp": float(undefended["T_true"][index]),
            },
            "reported": {"v": reported_v, "i": reported_i, "temp": reported_t},
            "predicted": {"v": estimated_v, "temp": estimated_t, "soc": estimated_soc},
            "residual": {
                "v": float(defended["innovation_v"][index]),
                "i": float(defended["innovation_i"][index]),
                "temp": float(defended["innovation_t"][index]),
            },
            "evidence": {
                "nis": float(defended["nis_window_sum"][index]),
                "nis_thr": float(config.detection.NIS_threshold),
                "cusum": {
                    "v": float(defended["cusum_v_score"][index]),
                    "i": float(defended["cusum_i_score"][index]),
                    "temp": float(defended["cusum_t_score"][index]),
                },
                "cusum_thr": float(config.detection.CUSUM_h),
                "probe": {
                    "active": bool(defended["probe_active"][index]),
                    "gain_v": defended["probe_gain_v"][index],
                    "gain_i": defended["probe_gain_i"][index],
                    "gain_min": float(config.probe.g_min_V),
                    "failed": bool(defended["probe_gain_alarm"][index]),
                },
                "cmd_unsafe": bool(defended["command_unsafe"][index]),
            },
            "state": str(defended["response_state"][index]),
            "localization": (
                localized[index]
                if localized is not None
                else {"channel": "unknown", "confidence": 0.0}
            ),
            "control": {
                "i_req": float(defended["I_req"][index]),
                "i_cmd": float(defended["I_cmd"][index]),
                "i_safe": float(defended["I_base_cmd"][index]),
                "mode": "derated"
                if str(defended["response_state"][index]) == "SAFE_MODE"
                else "normal",
            },
            "margins": {
                "temp": float(config.plant.T_hazard - defended["T_true"][index]),
                "v": float(config.plant.V_hazard - defended["V_true"][index]),
            },
            "attack": {
                "active": attack_active,
                "name": attack_name,
                "onset": onset,
            },
        }


def logger_info(event: str, **fields: object) -> None:
    import logging

    logging.getLogger("physiguard.api.sessions").info(
        json.dumps({"event": event, **fields}, separators=(",", ":"))
    )


def logger_error(event: str, **fields: object) -> None:
    import logging

    logging.getLogger("physiguard.api.sessions").error(
        json.dumps({"event": event, **fields}, separators=(",", ":"))
    )


async def websocket_session(websocket: WebSocket, manager: SessionManager, session_id: str) -> None:
    """Play a session while accepting validated pause, reset, and injection commands."""
    try:
        session = manager.get(session_id)
    except SessionError as exc:
        await websocket.accept()
        await websocket.send_json({"type": "error", "code": exc.code, "message": str(exc)})
        await websocket.close(code=4404)
        return
    await websocket.accept()
    scenario = next(item for item in load_scenarios().scenarios if item.id == session.scenario_id)
    await websocket.send_json(
        {
            "type": "hello",
            "version": "0.1.0",
            "config_hash": get_config().config_hash_short,
            "scenario": scenario.model_dump(mode="json"),
        }
    )
    try:
        while True:
            session.last_activity = time.monotonic()
            if session.status == "failed":
                await websocket.send_json(
                    {"type": "error", "code": "simulation_failed", "message": session.error}
                )
                return
            if (
                session.status == "ready"
                and not session.paused
                and session.cursor < session.total_steps
            ):
                speed = session.speed
                stop = min(session.cursor + speed, session.total_steps)
                indices = list(range(session.cursor, stop))
                if len(indices) > 10:
                    indices = [indices[round(i * (len(indices) - 1) / 9)] for i in range(10)]
                frames = [manager.frame(session, index) for index in indices]
                await websocket.send_json({"type": "frame_batch", "speed": speed, "frames": frames})
                session.cursor = stop
                current_defended = (
                    session.replacement_defended
                    if session.replacement_from is not None
                    and indices[-1] >= session.replacement_from
                    and session.replacement_defended is not None
                    else session.defended
                )
                assert current_defended is not None
                current_events = current_defended["events"]
                for event in current_events:
                    key = (float(event["time_s"]), str(event["code"]))
                    if key not in session.events_sent and key[0] <= float(frames[-1]["t"]):
                        session.events_sent.add(key)
                        await websocket.send_json(
                            {
                                "type": "event",
                                "t": key[0],
                                "kind": event["code"],
                                "severity": event["severity"],
                                "text": event["text"],
                                "data": {},
                            }
                        )
                if session.cursor >= session.total_steps:
                    session.status = "completed"
                    await websocket.send_json(
                        {
                            "type": "done",
                            "summary": {
                                "scenario_id": session.scenario_id,
                                "seed": session.seed,
                                "steps": session.total_steps,
                                "peak_temperature_c": float(max(current_defended["T_true"])),
                                "peak_voltage_v": float(max(current_defended["V_true"])),
                                "attack_detected": bool(any(current_defended["B3_alarm"])),
                            },
                        }
                    )
                await asyncio.sleep(1.0)
                try:
                    pending = await asyncio.wait_for(websocket.receive_text(), timeout=0.01)
                except TimeoutError:
                    continue
                await _handle_client_message(websocket, manager, session, pending)
                continue
            try:
                raw_text = await asyncio.wait_for(websocket.receive_text(), timeout=0.1)
            except TimeoutError:
                if session.task is not None and session.task.done() and session.status == "ready":
                    continue
                continue
            await _handle_client_message(websocket, manager, session, raw_text)
    except WebSocketDisconnect:
        session.last_activity = time.monotonic()


async def self_run(manager: SessionManager, session: SimulationSession, attack: str | None) -> None:
    await manager._run(session, attack)


async def _handle_client_message(
    websocket: WebSocket,
    manager: SessionManager,
    session: SimulationSession,
    raw_text: str,
) -> None:
    try:
        raw = json.loads(raw_text)
    except json.JSONDecodeError:
        await websocket.send_json(
            {"type": "error", "code": "invalid_message", "message": "Message must be valid JSON."}
        )
        return
    try:
        message = ClientMessage.model_validate(raw)
        if message.type == "pause":
            session.paused = True
        elif message.type == "resume":
            session.paused = False
        elif message.type == "speed":
            if message.value not in ALLOWED_SPEEDS:
                raise SessionError("speed.value must be one of 1, 5, 20, or 60")
            session.speed = int(message.value)
        elif message.type == "inject":
            if not message.attack:
                raise SessionError("inject requires an attack field")
            await manager.inject(session, message.attack, message.params or {})
            session.attack_id = message.attack
        elif message.type == "reset":
            session.seed = message.seed if message.seed is not None else session.seed
            session.cursor = 0
            session.paused = False
            session.replacement_from = None
            session.replacement_defended = None
            session.replacement_undefended = None
            session.replacement_localized = None
            session.attack_config_override = None
            original_scenario = next(
                item for item in load_scenarios().scenarios if item.id == session.scenario_id
            )
            session.attack_id = original_scenario.attack
            session.events_sent.clear()
            session.status = "queued"
            if session.task is not None and not session.task.done():
                session.task.cancel()
            session.task = asyncio.create_task(self_run(manager, session, session.attack_id))
        elif message.type == "operator_reset":
            accepted, completed, reason = await manager.request_operator_reset(session)
            await websocket.send_json(
                {
                    "type": "event",
                    "t": (
                        float(session.defended["t"][session.cursor])
                        if session.defended is not None and session.cursor < session.total_steps
                        else float(session.cursor)
                    ),
                    "kind": "operator_reset",
                    "severity": "info" if accepted else "warning",
                    "text": "Operator reset replay scheduled." if accepted else reason,
                    "data": {
                        "accepted": accepted,
                        "completed": completed,
                        "reason": reason,
                    },
                }
            )
    except (ValidationError, SessionError, ValueError) as exc:
        await websocket.send_json({"type": "error", "code": "invalid_message", "message": str(exc)})


def _localize_trace(trace: AttackTrajectory, attack_id: str) -> list[dict[str, Any]]:
    del attack_id
    config = get_config()
    engine = LocalizationEngine(config, load_localization_config())
    results: list[dict[str, Any]] = []
    for index in range(len(trace["t"])):
        output = engine.update(
            float(trace["V_rep"][index]),
            float(trace["I_rep"][index]),
            float(trace["T_rep"][index]),
            float(trace["I_cmd"][index]),
            bool(trace["B3_alarm"][index]),
            command_unsafe=bool(trace["command_unsafe"][index]),
        )
        results.append({"channel": output["channel"], "confidence": output["confidence"]})
    return results
