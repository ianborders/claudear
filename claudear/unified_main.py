"""Unified main entry point for multi-provider Claudear."""

import asyncio
import logging
import sys
from typing import Optional

import uvicorn

from claudear.core.app import print_banner, setup_ngrok
from claudear.core.config import get_settings, MultiProviderSettings

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
    ],
)

# Suppress noisy HTTP client logs
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)


def validate_config(settings: MultiProviderSettings) -> bool:
    """Validate configuration before starting.

    Args:
        settings: Application settings

    Returns:
        True if valid, False otherwise
    """
    errors = settings.validate()

    if errors:
        logger.error("Configuration errors:")
        for error in errors:
            logger.error(f"  - {error}")
        return False

    logger.info("Configuration validated successfully")
    return True


def main():
    """Main entry point for unified Claudear."""
    # Load settings
    try:
        settings = get_settings()
        logging.getLogger().setLevel(settings.log_level)
    except Exception as e:
        logger.error(f"Failed to load settings: {e}")
        logger.error("Make sure you have a .env file with required settings")
        sys.exit(1)

    # Validate configuration
    if not validate_config(settings):
        sys.exit(1)

    # Set up ngrok tunnel if configured
    public_url = setup_ngrok(settings)

    # Print startup banner
    print_banner(settings, public_url)

    # Show startup instructions
    if settings.has_linear():
        if public_url:
            print(f"📋 Register this webhook URL in Linear: {public_url}/webhooks/linear")
        else:
            print(
                f"📋 For local testing, use: http://localhost:{settings.webhook_port}/webhooks/linear"
            )
    print()

    # Run server
    logger.info(f"Starting server on {settings.webhook_host}:{settings.webhook_port}")

    uvicorn.run(
        "claudear.server.unified_app:unified_app",
        host=settings.webhook_host,
        port=settings.webhook_port,
        reload=False,
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":
    main()
