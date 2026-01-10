"""Unified application for multi-provider task automation."""

from __future__ import annotations

import asyncio
import atexit
import logging
import sys
from pathlib import Path
from typing import Optional

from claudear.core.config import get_settings, MultiProviderSettings
from claudear.core.types import ProviderType
from claudear.core.store import TaskStore
from claudear.core.orchestrator import TaskOrchestrator
from claudear.providers.base import PMProvider

logger = logging.getLogger(__name__)

# Track ngrok tunnel for cleanup
_ngrok_tunnel = None


def cleanup_ngrok():
    """Clean up ngrok tunnel on exit."""
    global _ngrok_tunnel
    if _ngrok_tunnel:
        try:
            from pyngrok import ngrok

            ngrok.disconnect(_ngrok_tunnel.public_url)
            ngrok.kill()
            logger.info("ngrok tunnel closed")
        except Exception:
            pass


def setup_ngrok(settings: MultiProviderSettings) -> Optional[str]:
    """Set up ngrok tunnel for webhook endpoint.

    Args:
        settings: Application settings

    Returns:
        Public URL or None if ngrok not available
    """
    global _ngrok_tunnel

    if not settings.ngrok_authtoken:
        logger.warning("NGROK_AUTHTOKEN not set, skipping ngrok setup")
        return None

    try:
        from pyngrok import conf, ngrok

        conf.get_default().auth_token = settings.ngrok_authtoken
        tunnel = ngrok.connect(settings.webhook_port, "http")
        _ngrok_tunnel = tunnel
        public_url = tunnel.public_url

        atexit.register(cleanup_ngrok)

        logger.info(f"ngrok tunnel established: {public_url}")
        return public_url

    except ImportError:
        logger.warning("pyngrok not installed, skipping ngrok setup")
        return None
    except Exception as e:
        logger.error(f"Failed to set up ngrok: {e}")
        return None


def print_banner(
    settings: MultiProviderSettings,
    public_url: Optional[str] = None,
):
    """Print startup banner with multi-provider info."""
    PURPLE = "\033[38;5;141m"
    BLUE = "\033[38;5;75m"
    GREEN = "\033[38;5;114m"
    YELLOW = "\033[38;5;221m"
    RESET = "\033[0m"

    banner = f"""{PURPLE}
╔════════════════════════════════════════════════════════════════════╗
║                                                                    ║
║  ██████╗██╗      █████╗ ██╗   ██╗██████╗ ███████╗ █████╗ ██████╗   ║
║ ██╔════╝██║     ██╔══██╗██║   ██║██╔══██╗██╔════╝██╔══██╗██╔══██╗  ║
║ ██║     ██║     ███████║██║   ██║██║  ██║█████╗  ███████║██████╔╝  ║
║ ██║     ██║     ██╔══██║██║   ██║██║  ██║██╔══╝  ██╔══██║██╔══██╗  ║
║ ╚██████╗███████╗██║  ██║╚██████╔╝██████╔╝███████╗██║  ██║██║  ██║  ║
║  ╚═════╝╚══════╝╚═╝  ╚═╝ ╚═════╝ ╚═════╝ ╚══════╝╚═╝  ╚═╝╚═╝  ╚═╝  ║
║                                                                    ║
║   Multi-Provider Autonomous Development Automation                 ║
║                                                                    ║
╚════════════════════════════════════════════════════════════════════╝{RESET}
"""
    print(banner)

    # Print provider info
    print(f"{BLUE}📋 Active Providers:{RESET}")

    if settings.has_linear():
        teams = settings.get_linear_team_ids()
        print(f"   {GREEN}✓ Linear{RESET}")
        for team_id in teams:
            instance = settings.get_linear_instance(team_id)
            if instance:
                print(f"     • Team {team_id} → {instance.repo_path}")

    if settings.has_notion():
        databases = settings.get_notion_database_ids()
        print(f"   {GREEN}✓ Notion{RESET}")
        for db_id in databases:
            instance = settings.get_notion_instance(db_id)
            if instance:
                short_id = db_id.replace("-", "")[:8]
                print(f"     • Database {short_id} → {instance.repo_path}")

    print()

    # Print webhook info
    if settings.has_linear():
        if public_url:
            print(f"{YELLOW}📡 Linear Webhook:{RESET} {public_url}/webhooks/linear")
        else:
            print(
                f"{YELLOW}📡 Linear Webhook:{RESET} http://localhost:{settings.webhook_port}/webhooks/linear"
            )

    print()
    print(f"{BLUE}⚙️  Settings:{RESET}")
    print(f"   Max concurrent tasks: {settings.max_concurrent_tasks}")
    print(f"   Comment poll interval: {settings.comment_poll_interval}s")
    if settings.has_notion():
        print(f"   Notion poll interval: {settings.notion_poll_interval}s")
    print()


class ClaudearApp:
    """Multi-provider Claudear application."""

    def __init__(self):
        """Initialize the application."""
        self.settings = get_settings()
        self.orchestrator: Optional[TaskOrchestrator] = None
        self._providers: dict[ProviderType, PMProvider] = {}

    async def initialize(self) -> None:
        """Initialize all providers and the orchestrator."""
        settings = self.settings

        # Validate configuration
        errors = settings.validate()
        if errors:
            logger.error("Configuration errors:")
            for error in errors:
                logger.error(f"  - {error}")
            raise ValueError("Invalid configuration")

        # Create task store
        store = TaskStore(settings.db_path)

        # Create orchestrator
        self.orchestrator = TaskOrchestrator(
            task_store=store,
            github_token=settings.github_token,
            max_concurrent_tasks=settings.max_concurrent_tasks,
            comment_poll_interval=settings.comment_poll_interval,
            blocked_timeout=settings.blocked_timeout,
        )

        # Initialize Linear provider if configured
        if settings.has_linear():
            await self._init_linear()

        # Initialize Notion provider if configured
        if settings.has_notion():
            await self._init_notion()

        logger.info("Application initialized")

    async def _init_linear(self) -> None:
        """Initialize Linear provider and teams."""
        settings = self.settings

        from claudear.providers.linear import LinearProvider

        provider = LinearProvider(
            api_key=settings.linear_api_key,
            labels_enabled=settings.linear_labels_enabled,
        )
        await provider.initialize()

        self._providers[ProviderType.LINEAR] = provider
        self.orchestrator.register_provider(provider)

        # Register each team
        for team_id in settings.get_linear_team_ids():
            instance = settings.get_linear_instance(team_id)
            if instance:
                await self.orchestrator.register_instance(instance)

        logger.info(
            f"Linear provider initialized with {len(settings.get_linear_team_ids())} team(s)"
        )

    async def _init_notion(self) -> None:
        """Initialize Notion provider and databases."""
        settings = self.settings

        from claudear.providers.notion import NotionProvider

        provider = NotionProvider(api_key=settings.notion_api_key)
        await provider.initialize()

        self._providers[ProviderType.NOTION] = provider
        self.orchestrator.register_provider(provider)

        # Register each database
        for db_id in settings.get_notion_database_ids():
            instance = settings.get_notion_instance(db_id)
            if instance:
                await self.orchestrator.register_instance(instance)

        logger.info(
            f"Notion provider initialized with {len(settings.get_notion_database_ids())} database(s)"
        )

    async def start(self) -> None:
        """Start the orchestrator and event sources."""
        if not self.orchestrator:
            raise RuntimeError("Application not initialized")

        await self.orchestrator.start()
        logger.info("Orchestrator started")

    async def stop(self) -> None:
        """Stop the orchestrator."""
        if self.orchestrator:
            await self.orchestrator.stop()
            logger.info("Orchestrator stopped")


# Global app instance for server access
_app: Optional[ClaudearApp] = None


def get_app() -> ClaudearApp:
    """Get the global application instance."""
    global _app
    if _app is None:
        _app = ClaudearApp()
    return _app


async def create_app() -> ClaudearApp:
    """Create and initialize the application."""
    app = get_app()
    await app.initialize()
    return app
