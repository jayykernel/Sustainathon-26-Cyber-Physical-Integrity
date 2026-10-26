"""FastAPI application factory for the PhysiGuard demo and benchmark API."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, cast

from fastapi import FastAPI, HTTPException, Request, Response, WebSocket
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from physiguard.attacks.base import load_attack_definitions
from physiguard.attacks.scenarios import load_scenarios
from physiguard.config import get_config, setup_logging
from physiguard.eval.report import RESULTS_DIR

from .sessions import (
    CreateSessionRequest,
    SessionError,
    SessionLimitError,
    SessionManager,
    websocket_session,
)

logger = logging.getLogger(__name__)
LIMITS: dict[str, Any] = {
    "threat_model": {
        "protected_assets": [
            "battery temperature",
            "terminal voltage",
            "state of charge",
            "charging current",
        ],
        "attacker_capabilities": [
            "temperature or voltage telemetry glitches and drift",
            "recorded telemetry replay with physical cooling degradation",
            "model-aware telemetry synthesis without access to the probe key or true actuator current",
            "malicious upstream current requests",
        ],
        "attacker_out_of_scope": [
            "direct battery hardware compromise",
            "cryptographic key extraction",
        ],
    },
    "method": {
        "state_estimation": "one-RC extended Kalman filter using voltage and temperature measurements",
        "passive_detection": "NIS, per-channel CUSUM, and physical range checks",
        "active_detection": "keyed current probes with voltage/current gain checks",
        "response": "pessimistic command guard with hysteretic response and operator reset",
    },
    "limitations": [
        "A2 oracle access to the true actuator current is outside the stated threat model.",
        "The evaluation is a simulated prototype and does not establish real-cell safety.",
        "False alarms remain material in the held-out evaluation and are reported without retuning.",
        "The S1 learned residual model was not implemented in this phase.",
    ],
}


def _error(code: str, message: str, status_code: int) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message}},
    )


def create_app() -> FastAPI:
    """Create the app, its bounded session manager, and the versioned API routes."""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        setup_logging()
        config = get_config()
        app.state.session_manager = SessionManager()
        cleanup_task = asyncio.create_task(_session_cleanup(app.state.session_manager))
        logger.info("PhysiGuard started config_hash=%s", config.config_hash_short)
        try:
            yield
        finally:
            cleanup_task.cancel()
            try:
                await cleanup_task
            except asyncio.CancelledError:
                pass
            cast(SessionManager, app.state.session_manager).close()

    app = FastAPI(title="PhysiGuard", version="0.1.0", lifespan=lifespan)
    if os.environ.get("PHYSIGUARD_DEV_CORS") == "1":
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
            allow_methods=["GET", "POST", "DELETE"],
            allow_headers=["Content-Type"],
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        return _error("validation_error", "Request body or parameters are invalid.", 422)

    @app.exception_handler(SessionLimitError)
    async def session_limit_error(_: Request, exc: SessionLimitError) -> JSONResponse:
        return _error(exc.code, str(exc), 429)

    @app.exception_handler(SessionError)
    async def session_error(_: Request, exc: SessionError) -> JSONResponse:
        status_code = 404 if str(exc).startswith("Session not found") else 400
        return _error(exc.code, str(exc), status_code)

    @app.exception_handler(HTTPException)
    async def http_error(_: Request, exc: HTTPException) -> JSONResponse:
        detail = str(exc.detail)
        code = "not_found" if exc.status_code == 404 else "http_error"
        if isinstance(exc.detail, dict):
            code = str(exc.detail.get("code", code))
            detail = str(exc.detail.get("message", detail))
        return _error(code, detail, exc.status_code)

    @app.exception_handler(Exception)
    async def unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled API error path=%s", request.url.path)
        return _error("internal_error", "The request could not be completed.", 500)

    @app.get("/api/health")
    async def health() -> dict[str, str | bool]:
        config = get_config()
        return {
            "status": "ok",
            "version": "0.1.0",
            "config_hash": config.config_hash_short,
            "thresholds_loaded": bool(config.detection.NIS_threshold),
        }

    @app.get("/api/scenarios")
    async def scenarios() -> list[dict[str, Any]]:
        catalog = load_scenarios()
        attack_config = load_attack_definitions()[1]
        captions: dict[str, list[str]] = {item.id: [] for item in catalog.scenarios}
        for step in catalog.story_ladder:
            captions[step.scenario_id].append(step.caption)
        return [
            {
                **scenario.model_dump(mode="json"),
                "level": "baseline"
                if scenario.attack is None
                else attack_config[scenario.attack].knowledge_level,
                "story_steps": captions[scenario.id],
            }
            for scenario in catalog.scenarios
        ]

    @app.post("/api/sessions", status_code=202)
    async def create_session(body: CreateSessionRequest) -> dict[str, str]:
        session = await app.state.session_manager.create(body)
        return {"session_id": session.session_id}

    @app.get("/api/sessions/{session_id}")
    async def get_session(session_id: str) -> dict[str, Any]:
        manager = cast(SessionManager, app.state.session_manager)
        session = manager.get(session_id)
        return manager.status(session)

    @app.delete("/api/sessions/{session_id}", status_code=204)
    async def delete_session(session_id: str) -> Response:
        if not app.state.session_manager.delete(session_id):
            raise HTTPException(
                status_code=404,
                detail={"code": "session_not_found", "message": "Session not found."},
            )
        return Response(status_code=204)

    @app.get("/api/benchmarks")
    async def benchmarks() -> dict[str, Any]:
        results_path, metadata_path = RESULTS_DIR / "results.json", RESULTS_DIR / "meta.json"
        if not results_path.is_file() or not metadata_path.is_file():
            raise HTTPException(
                status_code=404,
                detail={
                    "code": "benchmarks_missing",
                    "message": "Evaluation results are not available. Run the P7 evaluation first.",
                },
            )
        try:
            return {
                "results": json.loads(results_path.read_text(encoding="utf-8")),
                "meta": json.loads(metadata_path.read_text(encoding="utf-8")),
            }
        except (OSError, json.JSONDecodeError) as exc:
            raise HTTPException(
                status_code=503,
                detail={
                    "code": "benchmarks_invalid",
                    "message": "Evaluation artifacts could not be read.",
                },
            ) from exc

    @app.get("/api/limits")
    async def limits() -> dict[str, Any]:
        return LIMITS

    @app.websocket("/api/sessions/{session_id}/ws")
    async def session_socket(websocket: WebSocket, session_id: str) -> None:
        await websocket_session(websocket, app.state.session_manager, session_id)

    project_root = Path(__file__).resolve().parents[4]
    frontend_dist = project_root / "frontend" / "dist"
    if frontend_dist.is_dir():
        app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="frontend")
    return app


async def _session_cleanup(manager: SessionManager) -> None:
    while True:
        await asyncio.sleep(30)
        manager.cleanup_idle()


app = create_app()
