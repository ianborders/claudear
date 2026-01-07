"""FastAPI application for Claudear webhook server."""

import logging
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI

from claudear.config import get_settings
from claudear.git.github import GitHubClient
from claudear.git.worktree import WorktreeManager
from claudear.linear.client import LinearClient
from claudear.server.routes import health, webhooks
from claudear.tasks.manager import TaskManager
from claudear.tasks.store import TaskStore

logger = logging.getLogger(__name__)

# Global instances
_task_manager: Optional[TaskManager] = None


def get_task_manager() -> TaskManager:
    """Get the task manager instance."""
    if _task_manager is None:
        raise RuntimeError("Task manager not initialized")
    return _task_manager


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    global _task_manager

    settings = get_settings()

    # Initialize components
    linear_client = LinearClient(settings.linear_api_key)
    worktree_manager = WorktreeManager(
        repo_path=settings.repo_path,
        worktrees_dir=settings.worktrees_path,
    )
    github_client = GitHubClient(settings.github_token)
    task_store = TaskStore(settings.db_path)

    # Create task manager
    _task_manager = TaskManager(
        settings=settings,
        linear_client=linear_client,
        worktree_manager=worktree_manager,
        github_client=github_client,
        task_store=task_store,
    )

    # Start task manager
    await _task_manager.start()
    logger.info("Claudear server started")

    yield

    # Shutdown
    await _task_manager.stop()
    logger.info("Claudear server stopped")


def create_app() -> FastAPI:
    """Create the FastAPI application."""
    app = FastAPI(
        title="Claudear",
        description="Autonomous development automation with Claude Code and Linear",
        version="0.1.0",
        lifespan=lifespan,
    )

    # Include routers
    app.include_router(health.router, tags=["Health"])
    app.include_router(webhooks.router, prefix="/webhooks", tags=["Webhooks"])

    return app


# Create app instance
app = create_app()
