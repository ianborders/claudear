#!/usr/bin/env python3
"""Script to register Linear webhook."""

import asyncio
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from claudiar.config import get_settings
from claudiar.linear.client import LinearClient


async def main():
    """Register webhook with Linear."""
    settings = get_settings()

    # Get webhook URL from user
    print("Linear Webhook Registration")
    print("=" * 40)
    print()

    webhook_url = input("Enter your ngrok public URL (e.g., https://abc123.ngrok.io): ").strip()

    if not webhook_url:
        print("Error: Webhook URL is required")
        sys.exit(1)

    if not webhook_url.startswith("https://"):
        print("Error: Webhook URL must start with https://")
        sys.exit(1)

    # Add webhook path
    full_url = f"{webhook_url.rstrip('/')}/webhooks/linear"

    print(f"\nRegistering webhook: {full_url}")
    print(f"Team ID: {settings.linear_team_id}")
    print()

    # Create webhook
    client = LinearClient(settings.linear_api_key)

    try:
        result = await client.create_webhook(
            url=full_url,
            team_id=settings.linear_team_id,
            resource_types=["Issue", "Comment"],
        )

        if result.get("success"):
            webhook = result.get("webhook", {})
            print("✅ Webhook registered successfully!")
            print(f"   ID: {webhook.get('id')}")
            print(f"   URL: {webhook.get('url')}")

            # Update .env with webhook secret if returned
            secret = webhook.get("secret")
            if secret:
                print(f"\n📝 Update your .env file with:")
                print(f"   LINEAR_WEBHOOK_SECRET={secret}")
        else:
            print("❌ Failed to register webhook")
            print(f"   Result: {result}")

    except Exception as e:
        print(f"❌ Error registering webhook: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
