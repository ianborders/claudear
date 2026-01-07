"""Main entry point for Claudear."""

import asyncio
import atexit
import logging
import signal
import sys
from pathlib import Path
from typing import Optional

import uvicorn

from claudear.config import get_settings

# Track ngrok tunnel for cleanup
_ngrok_tunnel = None

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
    ],
)

logger = logging.getLogger(__name__)


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


def setup_ngrok() -> Optional[str]:
    """Set up ngrok tunnel for webhook endpoint.

    Returns:
        Public URL or None if ngrok not available
    """
    global _ngrok_tunnel
    settings = get_settings()

    if not settings.ngrok_authtoken:
        logger.warning("NGROK_AUTHTOKEN not set, skipping ngrok setup")
        return None

    try:
        from pyngrok import conf, ngrok

        # Configure ngrok
        conf.get_default().auth_token = settings.ngrok_authtoken

        # Create tunnel
        tunnel = ngrok.connect(settings.webhook_port, "http")
        _ngrok_tunnel = tunnel
        public_url = tunnel.public_url

        # Register cleanup
        atexit.register(cleanup_ngrok)

        logger.info(f"ngrok tunnel established: {public_url}")
        logger.info(f"Webhook URL: {public_url}/webhooks/linear")

        return public_url

    except ImportError:
        logger.warning("pyngrok not installed, skipping ngrok setup")
        return None
    except Exception as e:
        logger.error(f"Failed to set up ngrok: {e}")
        return None


def print_banner():
    """Print startup banner."""
    # Light purple color
    PURPLE = "\033[38;5;141m"
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
║   Autonomous Development Automation with Claude Code & Linear      ║
║                                                                    ║
╚════════════════════════════════════════════════════════════════════╝{RESET}
"""
    print(banner)


def validate_config():
    """Validate configuration before starting."""
    settings = get_settings()

    errors = []

    # Check required settings
    if not settings.linear_api_key:
        errors.append("LINEAR_API_KEY is required")
    if not settings.linear_webhook_secret:
        errors.append("LINEAR_WEBHOOK_SECRET is required")
    if not settings.linear_team_id:
        errors.append("LINEAR_TEAM_ID is required")
    if not settings.github_token:
        errors.append("GITHUB_TOKEN is required")

    # Check repo path exists
    if settings.repo_path:
        repo_path = Path(settings.repo_path)
        if not repo_path.exists():
            errors.append(f"REPO_PATH does not exist: {settings.repo_path}")
        elif not (repo_path / ".git").exists():
            errors.append(f"REPO_PATH is not a git repository: {settings.repo_path}")

    if errors:
        logger.error("Configuration errors:")
        for error in errors:
            logger.error(f"  - {error}")
        sys.exit(1)

    logger.info("Configuration validated successfully")


def main():
    """Main entry point."""
    print_banner()

    # Load and validate settings
    try:
        settings = get_settings()
        logging.getLogger().setLevel(settings.log_level)
    except Exception as e:
        logger.error(f"Failed to load settings: {e}")
        logger.error("Make sure you have a .env file with required settings")
        sys.exit(1)

    validate_config()

    # Set up ngrok tunnel
    public_url = setup_ngrok()
    if public_url:
        print(f"\n📡 Webhook URL: {public_url}/webhooks/linear")
        print("   Register this URL in your Linear webhook settings\n")
    else:
        print(f"\n⚠️  No ngrok tunnel - webhooks will only work on localhost:{settings.webhook_port}")
        print(f"   Local webhook URL: http://localhost:{settings.webhook_port}/webhooks/linear\n")

    print(f"📂 Repository: {settings.repo_path}")
    print(f"🔄 Max concurrent tasks: {settings.max_concurrent_tasks}")
    print(f"⏱️  Comment poll interval: {settings.comment_poll_interval}s")
    print()

    # Run server
    logger.info(f"Starting server on {settings.webhook_host}:{settings.webhook_port}")

    uvicorn.run(
        "claudear.server.app:app",
        host=settings.webhook_host,
        port=settings.webhook_port,
        reload=False,
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":
    main()
