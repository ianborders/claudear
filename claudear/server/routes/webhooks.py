"""Linear webhook endpoints."""

import hashlib
import hmac
import logging
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Request

from claudear.config import get_settings
from claudear.linear.models import WebhookPayload

logger = logging.getLogger(__name__)


def get_task_manager():
    """Get task manager - imported lazily to avoid circular import."""
    from claudear.server.app import get_task_manager as _get_task_manager
    return _get_task_manager()

router = APIRouter()


async def verify_signature(
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

    # Compute expected signature
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

    Args:
        request: FastAPI request
        background_tasks: Background task runner
        linear_signature: Webhook signature header
        linear_event: Event type header
        linear_delivery: Delivery ID header

    Returns:
        Acceptance response
    """
    settings = get_settings()

    # Verify signature
    body = await verify_signature(request, linear_signature)

    # Parse payload
    try:
        import json

        data = json.loads(body)
        payload = WebhookPayload(**data)
    except Exception as e:
        logger.error(f"Failed to parse webhook payload: {e}")
        raise HTTPException(status_code=400, detail="Invalid payload")

    logger.info(
        f"Received webhook: type={payload.type}, action={payload.action}, "
        f"delivery={linear_delivery}"
    )

    # Handle different event types
    if payload.type == "Issue":
        await _handle_issue_event(payload, background_tasks)
    elif payload.type == "Comment":
        await _handle_comment_event(payload, background_tasks)
    else:
        logger.debug(f"Ignoring webhook type: {payload.type}")

    return {"status": "accepted", "delivery": linear_delivery}


async def _handle_issue_event(
    payload: WebhookPayload, background_tasks: BackgroundTasks
) -> None:
    """Handle issue webhook events.

    Args:
        payload: Webhook payload
        background_tasks: Background task runner
    """
    settings = get_settings()

    # Only handle updates (state changes)
    if payload.action != "update":
        return

    # Check if this is a state change
    if not payload.is_state_change():
        return

    # Get issue data
    issue = payload.get_issue()
    if not issue:
        logger.warning("Could not extract issue from webhook")
        return

    new_state_id = payload.get_new_state_id()
    if not new_state_id:
        logger.warning("Could not determine new state")
        return

    logger.info(
        f"Issue {issue.identifier} state changed, new state ID: {new_state_id}"
    )

    # Handle in background to respond quickly
    task_manager = get_task_manager()
    background_tasks.add_task(
        task_manager.handle_issue_update,
        issue,
        new_state_id,
    )


async def _handle_comment_event(
    payload: WebhookPayload, background_tasks: BackgroundTasks
) -> None:
    """Handle comment webhook events.

    Args:
        payload: Webhook payload
        background_tasks: Background task runner
    """
    # Only handle new comments
    if payload.action != "create":
        return

    # Extract comment data
    comment_data = payload.data
    issue_id = comment_data.get("issueId")
    body = comment_data.get("body", "")
    user_data = comment_data.get("user", {})
    user_id = user_data.get("id", "")

    if not issue_id:
        logger.warning("Comment webhook missing issueId")
        return

    logger.info(f"New comment on issue {issue_id}")

    # Handle in background
    task_manager = get_task_manager()
    background_tasks.add_task(
        task_manager.handle_comment,
        issue_id,
        body,
        user_id,
    )


@router.get("/linear/test")
async def test_webhook():
    """Test endpoint for webhook connectivity."""
    return {
        "status": "ok",
        "message": "Webhook endpoint is reachable",
    }
