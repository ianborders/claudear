#!/usr/bin/env python3
"""Script to test webhook endpoint."""

import hashlib
import hmac
import json
import sys
from datetime import datetime
from pathlib import Path

import httpx

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))


def main():
    """Send a test webhook to the local server."""
    print("Webhook Test")
    print("=" * 40)
    print()

    try:
        from claudear.config import get_settings

        settings = get_settings()
    except Exception as e:
        print(f"Error loading settings: {e}")
        sys.exit(1)

    # Test payload
    payload = {
        "action": "update",
        "type": "Issue",
        "createdAt": datetime.now().isoformat(),
        "data": {
            "id": "test-issue-id",
            "identifier": "TEST-1",
            "title": "Test Issue",
            "description": "This is a test issue",
            "teamId": settings.linear_team_id,
            "stateId": "new-state-id",
        },
        "updatedFrom": {
            "stateId": "old-state-id",
        },
    }

    body = json.dumps(payload)

    # Calculate signature
    signature = hmac.new(
        settings.linear_webhook_secret.encode(),
        body.encode(),
        hashlib.sha256,
    ).hexdigest()

    # Send request
    url = f"http://localhost:{settings.webhook_port}/webhooks/linear"

    print(f"Sending test webhook to: {url}")
    print(f"Payload: {json.dumps(payload, indent=2)}")
    print()

    try:
        response = httpx.post(
            url,
            content=body,
            headers={
                "Content-Type": "application/json",
                "Linear-Signature": signature,
                "Linear-Event": "Issue",
                "Linear-Delivery": "test-delivery-id",
            },
        )

        print(f"Response status: {response.status_code}")
        print(f"Response body: {response.text}")

        if response.status_code == 200:
            print("\n✅ Webhook test successful!")
        else:
            print(f"\n❌ Webhook test failed: {response.status_code}")

    except httpx.ConnectError:
        print(f"\n❌ Could not connect to {url}")
        print("   Make sure the Claudear server is running")
    except Exception as e:
        print(f"\n❌ Error: {e}")


if __name__ == "__main__":
    main()
