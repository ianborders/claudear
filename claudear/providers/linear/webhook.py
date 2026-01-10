"""Linear webhook event source for multi-team support."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Callable, Any, Optional, TYPE_CHECKING

from claudear.providers.base import EventSource, EventSourceMode
from claudear.core.types import TaskId, TaskStatus, ProviderType, ProviderInstance
from claudear.events.types import (
    Event,
    TaskStatusChangedEvent,
    TaskCommentAddedEvent,
    TaskUpdatedEvent,
)
from claudear.linear.models import WebhookPayload

if TYPE_CHECKING:
    from claudear.providers.linear.provider import LinearProvider

logger = logging.getLogger(__name__)


class LinearWebhookEventSource(EventSource):
    """Webhook event source for a Linear team.

    Converts Linear webhook payloads to unified Event types.
    One instance per team for proper event routing.
    """

    def __init__(
        self,
        provider: "LinearProvider",
        instance: ProviderInstance,
    ):
        """Initialize the event source.

        Args:
            provider: Parent LinearProvider
            instance: Team configuration
        """
        self._provider = provider
        self._instance = instance
        self._handler: Optional[Callable[[Event], Any]] = None
        self._bot_user_id: Optional[str] = None

    @property
    def mode(self) -> EventSourceMode:
        return EventSourceMode.WEBHOOK

    @property
    def team_id(self) -> str:
        """Get the team ID this event source handles."""
        return self._instance.instance_id

    async def start(self) -> None:
        """Start receiving events.

        For webhooks, this caches the bot user ID for comment filtering.
        Webhook registration is handled separately by the server.
        """
        # Cache bot user ID for filtering bot comments
        try:
            self._bot_user_id = await self._provider.client.get_bot_user_id()
            logger.info(
                f"Linear webhook event source started for team {self.team_id}"
            )
        except Exception as e:
            logger.error(f"Failed to get bot user ID: {e}")

    async def stop(self) -> None:
        """Stop receiving events.

        For webhooks, cleanup is minimal - the server handles unregistration.
        """
        logger.info(f"Linear webhook event source stopped for team {self.team_id}")

    def set_event_handler(self, handler: Callable[[Event], Any]) -> None:
        """Set the callback for received events.

        Args:
            handler: Async function called with each Event
        """
        self._handler = handler

    async def handle_webhook(self, payload: WebhookPayload) -> None:
        """Process a Linear webhook payload.

        Called by the webhook route after signature verification.
        Converts the payload to unified events and dispatches to handler.

        Args:
            payload: Parsed webhook payload
        """
        if not self._handler:
            logger.warning("No event handler registered, dropping webhook")
            return

        if payload.type == "Issue":
            await self._handle_issue_webhook(payload)
        elif payload.type == "Comment":
            await self._handle_comment_webhook(payload)
        else:
            logger.debug(f"Ignoring webhook type: {payload.type}")

    async def _handle_issue_webhook(self, payload: WebhookPayload) -> None:
        """Handle an issue webhook.

        Args:
            payload: Webhook payload
        """
        issue = payload.get_issue()
        if not issue:
            logger.warning("Could not extract issue from webhook")
            return

        # Verify this issue belongs to our team
        if issue.team_id and issue.team_id != self._instance.instance_id:
            # Try resolving team key to UUID
            try:
                team_uuid = await self._provider.client.get_team_uuid(
                    self._instance.instance_id
                )
                if issue.team_id != team_uuid:
                    logger.debug(
                        f"Issue {issue.identifier} belongs to team {issue.team_id}, "
                        f"not {self._instance.instance_id}"
                    )
                    return
            except Exception:
                # If we can't verify, accept it
                pass

        # Create task ID
        task_id = TaskId(
            provider=ProviderType.LINEAR,
            instance_id=self._instance.instance_id,
            external_id=issue.id,
            identifier=issue.identifier,
        )

        if payload.action == "update" and payload.is_state_change():
            await self._handle_state_change(payload, task_id, issue)
        elif payload.action in ("create", "update"):
            await self._handle_issue_update(payload, task_id, issue)

    async def _handle_state_change(
        self,
        payload: WebhookPayload,
        task_id: TaskId,
        issue: Any,
    ) -> None:
        """Handle an issue state change.

        Args:
            payload: Webhook payload
            task_id: Unified task ID
            issue: Issue data from webhook
        """
        new_state_id = payload.get_new_state_id()
        old_state_id = payload.get_previous_state_id()

        if not new_state_id:
            logger.warning("Could not determine new state")
            return

        # Convert state IDs to TaskStatus
        new_status = await self._provider.detect_status(task_id, new_state_id)
        old_status = None
        if old_state_id:
            old_status = await self._provider.detect_status(task_id, old_state_id)

        event = TaskStatusChangedEvent(
            task_id=task_id,
            timestamp=payload.created_at,
            old_status=old_status,
            new_status=new_status,
            task_title=issue.title,
            task_description=issue.description,
            raw_data={
                "action": payload.action,
                "new_state_id": new_state_id,
                "old_state_id": old_state_id,
            },
        )

        logger.info(
            f"Issue {issue.identifier} state changed: "
            f"{old_status.value if old_status else 'unknown'} -> {new_status.value}"
        )

        await self._dispatch_event(event)

    async def _handle_issue_update(
        self,
        payload: WebhookPayload,
        task_id: TaskId,
        issue: Any,
    ) -> None:
        """Handle a general issue update.

        Args:
            payload: Webhook payload
            task_id: Unified task ID
            issue: Issue data from webhook
        """
        updated_fields = []
        if payload.updated_from:
            updated_fields = list(payload.updated_from.keys())

        # Filter out state changes (handled separately)
        if "stateId" in updated_fields:
            updated_fields.remove("stateId")

        if not updated_fields:
            return

        event = TaskUpdatedEvent(
            task_id=task_id,
            timestamp=payload.created_at,
            updated_fields=updated_fields,
            new_title=issue.title if "title" in updated_fields else None,
            new_description=issue.description if "description" in updated_fields else None,
            raw_data={"action": payload.action, "updated_from": payload.updated_from},
        )

        logger.debug(f"Issue {issue.identifier} updated: {updated_fields}")
        await self._dispatch_event(event)

    async def _handle_comment_webhook(self, payload: WebhookPayload) -> None:
        """Handle a comment webhook.

        Args:
            payload: Webhook payload
        """
        if payload.action != "create":
            return

        comment_data = payload.data
        issue_id = comment_data.get("issueId")
        body = comment_data.get("body", "")
        user_data = comment_data.get("user", {})
        user_id = user_data.get("id", "")
        user_name = user_data.get("name")

        if not issue_id:
            logger.warning("Comment webhook missing issueId")
            return

        # Check if this is a bot comment
        is_bot = user_id == self._bot_user_id if self._bot_user_id else False

        # We need the issue identifier - fetch it if needed
        # For now, use issue_id as identifier (will be resolved by orchestrator)
        task_id = TaskId(
            provider=ProviderType.LINEAR,
            instance_id=self._instance.instance_id,
            external_id=issue_id,
            identifier="",  # Will be resolved later
        )

        event = TaskCommentAddedEvent(
            task_id=task_id,
            timestamp=payload.created_at,
            comment_body=body,
            comment_author_id=user_id,
            comment_author_name=user_name,
            is_bot_comment=is_bot,
            raw_data={"action": payload.action, "comment": comment_data},
        )

        logger.info(
            f"New comment on issue {issue_id} from "
            f"{'bot' if is_bot else user_name or user_id}"
        )

        await self._dispatch_event(event)

    async def _dispatch_event(self, event: Event) -> None:
        """Dispatch an event to the registered handler.

        Args:
            event: Event to dispatch
        """
        if self._handler:
            try:
                result = self._handler(event)
                # Handle both sync and async handlers
                if hasattr(result, "__await__"):
                    await result
            except Exception as e:
                logger.error(f"Event handler error: {e}")
