"""FastAPI application factory."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from physiguard.config import get_config, setup_logging

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        setup_logging()
        config = get_config()
        logger.info("PhysiGuard started config_hash=%s", config.config_hash_short)
        yield

    app = FastAPI(title="PhysiGuard", version="0.1.0", lifespan=lifespan)

    @app.get("/api/health")
    async def health() -> dict[str, str | bool]:
        """Health check endpoint."""
        config = get_config()
        return {
            "status": "ok",
            "version": "0.1.0",
            "config_hash": config.config_hash_short,
            "thresholds_loaded": bool(config.detection.NIS_threshold),
        }

    return app


# For ASGI servers like uvicorn
app = create_app()
