"""Unified FastAPI application for multi-provider Claudear server."""

import logging
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI

from claudear.core.app import ClaudearApp, get_app
from claudear.core.config import get_settings
from claudear.core.orchestrator import TaskOrchestrator

logger = logging.getLogger(__name__)

# Global orchestrator reference for webhook handlers
_orchestrator: Optional[TaskOrchestrator] = None


def get_orchestrator() -> TaskOrchestrator:
    """Get the task orchestrator instance."""
    if _orchestrator is None:
        raise RuntimeError("Orchestrator not initialized")
    return _orchestrator


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    global _orchestrator

    # Initialize the Claudear application
    claudear_app = get_app()
    await claudear_app.initialize()

    _orchestrator = claudear_app.orchestrator

    # Start the orchestrator
    await claudear_app.start()
    logger.info("Claudear unified server started")

    # Log active instances
    for info in _orchestrator.get_instance_info():
        logger.info(
            f"Active: {info['provider']}/{info['instance_id']} → {info['repo_path']}"
        )

    yield

    # Shutdown
    await claudear_app.stop()
    logger.info("Claudear unified server stopped")


def create_unified_app() -> FastAPI:
    """Create the unified FastAPI application."""
    from claudear.server.routes import health
    from claudear.server.routes.unified_webhooks import router as webhook_router

    app = FastAPI(
        title="Claudear",
        description="Multi-provider autonomous development automation",
        version="0.2.0",
        lifespan=lifespan,
    )

    # Include routers
    app.include_router(health.router, tags=["Health"])
    app.include_router(webhook_router, prefix="/webhooks", tags=["Webhooks"])

    return app


# Create app instance
unified_app = create_unified_app()
