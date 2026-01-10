"""Unified webhook endpoints for multi-provider Claudear."""

import hashlib
import hmac
import logging
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Request

from claudear.core.config import get_settings
from claudear.core.types import ProviderType
from claudear.linear.models import WebhookPayload

logger = logging.getLogger(__name__)

router = APIRouter()


def get_orchestrator():
    """Get orchestrator - imported lazily to avoid circular import."""
    from claudear.server.unified_app import get_orchestrator as _get_orchestrator

    return _get_orchestrator()


async def verify_linear_signature(
    request: Request,
    linear_signature: Optional[str] = Header(None, alias="Linear-Signature"),
) -> bytes:
    """Verify the Linear webhook signature.

    Args:
        request: FastAPI request
        linear_signature: Signature from Linear header

    Returns:
        Request body bytes

    Raises:
        HTTPException: If signature is invalid
    """
    settings = get_settings()

    body = await request.body()

    if not linear_signature:
        logger.warning("Missing Linear-Signature header")
        raise HTTPException(status_code=401, detail="Missing signature")

    if not settings.linear_webhook_secret:
        logger.error("LINEAR_WEBHOOK_SECRET not configured")
        raise HTTPException(status_code=500, detail="Webhook secret not configured")

    expected = hmac.new(
        settings.linear_webhook_secret.encode(),
        body,
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(linear_signature, expected):
        logger.warning("Invalid webhook signature")
        raise HTTPException(status_code=401, detail="Invalid signature")

    return body


@router.post("/linear")
async def linear_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    linear_signature: Optional[str] = Header(None, alias="Linear-Signature"),
    linear_event: Optional[str] = Header(None, alias="Linear-Event"),
    linear_delivery: Optional[str] = Header(None, alias="Linear-Delivery"),
):
    """Handle Linear webhook events.

    Routes events to the appropriate team's event source based on team_id.

    Args:
        request: FastAPI request
        background_tasks: Background task runner
        linear_signature: Webhook signature header
        linear_event: Event type header
        linear_delivery: Delivery ID header

    Returns:
        Acceptance response
    """
    # Verify signature
    body = await verify_linear_signature(request, linear_signature)

    # Parse payload
    try:
        import json

        data = json.loads(body)
        payload = WebhookPayload(**data)
    except Exception as e:
        logger.error(f"Failed to parse webhook payload: {e}")
        raise HTTPException(status_code=400, detail="Invalid payload")

    logger.info(
        f"Received Linear webhook: type={payload.type}, action={payload.action}, "
        f"delivery={linear_delivery}"
    )

    # Extract team_id from payload
    team_id = None
    if payload.type == "Issue":
        issue = payload.get_issue()
        if issue:
            team_id = issue.team_id
    elif payload.type == "Comment":
        # Comments include issueId but not team directly
        # We'll need to look up the issue to get the team
        pass

    if not team_id:
        # Try to get team from data directly
        team_id = payload.data.get("teamId")

    if not team_id:
        logger.warning("Could not determine team_id from webhook, using default")
        # Fall back to first configured team
        settings = get_settings()
        teams = settings.get_linear_team_ids()
        if teams:
            team_id = teams[0]
        else:
            logger.error("No Linear teams configured")
            return {"status": "ignored", "reason": "No teams configured"}

    # Route to appropriate event source
    background_tasks.add_task(_handle_linear_webhook, payload, team_id)

    return {"status": "accepted", "delivery": linear_delivery}


async def _handle_linear_webhook(payload: WebhookPayload, team_id: str) -> None:
    """Handle a Linear webhook in the background.

    Args:
        payload: Parsed webhook payload
        team_id: Team ID/key for routing
    """
    try:
        orchestrator = get_orchestrator()

        # Find the Linear provider
        from claudear.providers.linear import LinearProvider

        provider = None
        for p in orchestrator._providers.values():
            if isinstance(p, LinearProvider):
                provider = p
                break

        if not provider:
            logger.warning("No Linear provider registered")
            return

        # Get the event source for this team
        from claudear.core.types import ProviderInstance

        key = (ProviderType.LINEAR, team_id)
        resources = orchestrator._instance_resources.get(key)

        if not resources:
            # Try with team UUID instead of key
            logger.warning(f"No resources for team {team_id}, trying lookup")
            # Check all Linear instances
            for k, r in orchestrator._instance_resources.items():
                if k[0] == ProviderType.LINEAR:
                    # This is a Linear instance, check if team_id matches
                    resources = r
                    break

        if not resources:
            logger.warning(f"No instance registered for team {team_id}")
            return

        event_source = provider.get_event_source(resources.instance)

        # Route to event source for processing
        from claudear.providers.linear.webhook import LinearWebhookEventSource

        if isinstance(event_source, LinearWebhookEventSource):
            await event_source.handle_webhook(payload)
        else:
            logger.warning(f"Unexpected event source type: {type(event_source)}")

    except Exception as e:
        logger.error(f"Error handling Linear webhook: {e}")


@router.get("/linear/test")
async def test_linear_webhook():
    """Test endpoint for Linear webhook connectivity."""
    return {
        "status": "ok",
        "message": "Linear webhook endpoint is reachable",
    }


@router.get("/health")
async def webhook_health():
    """Health check for webhook endpoints."""
    settings = get_settings()

    return {
        "status": "healthy",
        "providers": {
            "linear": settings.has_linear(),
            "notion": settings.has_notion(),
        },
    }
