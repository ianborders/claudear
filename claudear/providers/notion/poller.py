"""Notion polling event source for change detection."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Callable, Any, Optional, TYPE_CHECKING

from claudear.providers.base import EventSource, EventSourceMode
from claudear.core.types import TaskId, TaskStatus, ProviderType, ProviderInstance
from claudear.events.types import (
    Event,
    TaskStatusChangedEvent,
    TaskCommentAddedEvent,
)

if TYPE_CHECKING:
    from claudear.providers.notion.provider import NotionProvider

logger = logging.getLogger(__name__)


class NotionPollerEventSource(EventSource):
    """Polling event source for a Notion database.

    Polls the database for status changes and emits unified events.
    One instance per database for proper event routing.
    """

    def __init__(
        self,
        provider: "NotionProvider",
        instance: ProviderInstance,
        poll_interval: int = 5,
    ):
        """Initialize the event source.

        Args:
            provider: Parent NotionProvider
            instance: Database configuration
            poll_interval: Polling interval in seconds
        """
        self._provider = provider
        self._instance = instance
        self._poll_interval = poll_interval
        self._handler: Optional[Callable[[Event], Any]] = None

        # Polling state
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._page_states: dict[str, str] = {}  # page_id -> status
        self._comment_timestamps: dict[str, datetime] = {}  # page_id -> last check
        self._pages_to_watch_comments: set[str] = set()

    @property
    def mode(self) -> EventSourceMode:
        return EventSourceMode.POLLING

    @property
    def database_id(self) -> str:
        """Get the database ID this event source handles."""
        return self._instance.instance_id

    async def start(self) -> None:
        """Start the polling loop."""
        if self._running:
            logger.warning(
                f"Poller already running for database {self.database_id}"
            )
            return

        # Initialize state before starting to avoid false triggers
        await self._initialize_state()

        self._running = True
        self._task = asyncio.create_task(self._poll_loop())
        logger.info(
            f"Started Notion poller for database {self.database_id} "
            f"(interval: {self._poll_interval}s)"
        )

    async def stop(self) -> None:
        """Stop the polling loop."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info(f"Stopped Notion poller for database {self.database_id}")

    def set_event_handler(self, handler: Callable[[Event], Any]) -> None:
        """Set the callback for received events.

        Args:
            handler: Async function called with each Event
        """
        self._handler = handler

    def watch_comments(self, page_id: str) -> None:
        """Start watching a page for new comments.

        Args:
            page_id: Page ID to watch (typically blocked pages)
        """
        self._pages_to_watch_comments.add(page_id)
        self._comment_timestamps[page_id] = datetime.now()
        logger.debug(f"Now watching page {page_id} for comments")

    def unwatch_comments(self, page_id: str) -> None:
        """Stop watching a page for comments.

        Args:
            page_id: Page ID to stop watching
        """
        self._pages_to_watch_comments.discard(page_id)
        self._comment_timestamps.pop(page_id, None)
        logger.debug(f"Stopped watching page {page_id} for comments")

    async def _initialize_state(self) -> None:
        """Initialize state by reading current page statuses.

        This prevents false triggers when the poller starts.
        """
        logger.info(f"Initializing poller state for database {self.database_id}")

        try:
            pages = await self._provider.client.query_pages(
                self.database_id,
                filter={
                    "property": "Status",
                    "status": {"does_not_equal": "Backlog"},
                },
            )

            for page in pages:
                self._page_states[page.id] = page.status or ""

            logger.info(f"Initialized state for {len(pages)} pages")

        except Exception as e:
            logger.error(f"Failed to initialize poller state: {e}")

    async def _poll_loop(self) -> None:
        """Main polling loop."""
        while self._running:
            try:
                await self._poll_once()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in poll loop for {self.database_id}: {e}")

            await asyncio.sleep(self._poll_interval)

    async def _poll_once(self) -> None:
        """Perform a single poll iteration."""
        # Query active pages (not in Backlog)
        pages = await self._provider.client.query_pages(
            self.database_id,
            filter={
                "property": "Status",
                "status": {"does_not_equal": "Backlog"},
            },
        )

        # Check for status changes
        for page in pages:
            old_status = self._page_states.get(page.id)
            new_status = page.status

            # First time seeing this page
            if old_status is None:
                self._page_states[page.id] = new_status or ""
                old_status = "Backlog"  # Treat as moved from Backlog

            # Status changed
            if old_status != new_status:
                self._page_states[page.id] = new_status or ""
                await self._emit_status_change(page, old_status, new_status)

        # Check for pages moved back to Backlog
        backlog_pages = await self._provider.client.query_pages(
            self.database_id,
            filter={
                "property": "Status",
                "status": {"equals": "Backlog"},
            },
        )

        for page in backlog_pages:
            if page.id in self._page_states:
                old_status = self._page_states.pop(page.id)
                if old_status != "Backlog":
                    logger.info(f"Page {page.title} moved back to Backlog")

        # Check for new comments on watched pages
        await self._check_comments()

    async def _emit_status_change(
        self,
        page: Any,  # NotionPage
        old_status: Optional[str],
        new_status: Optional[str],
    ) -> None:
        """Emit a status change event.

        Args:
            page: The Notion page
            old_status: Previous status name
            new_status: New status name
        """
        if not self._handler:
            return

        # Create task ID
        task_id = TaskId(
            provider=ProviderType.NOTION,
            instance_id=self.database_id,
            external_id=page.id,
            identifier=page.claudear_id or page.id[:8],
        )

        # Convert status names to TaskStatus
        old_task_status = await self._provider.detect_status(task_id, old_status or "")
        new_task_status = await self._provider.detect_status(
            task_id, new_status or ""
        )

        event = TaskStatusChangedEvent(
            task_id=task_id,
            timestamp=datetime.now(),
            old_status=old_task_status,
            new_status=new_task_status,
            task_title=page.title,
            task_description=None,  # Would require additional API call
            raw_data={
                "old_status_name": old_status,
                "new_status_name": new_status,
                "page_url": page.url,
            },
        )

        logger.info(
            f"Page {page.title} status changed: "
            f"{old_status} -> {new_status} "
            f"({old_task_status.value} -> {new_task_status.value})"
        )

        await self._dispatch_event(event)

    async def _check_comments(self) -> None:
        """Check for new comments on watched pages."""
        if not self._pages_to_watch_comments or not self._handler:
            return

        for page_id in list(self._pages_to_watch_comments):
            since = self._comment_timestamps.get(page_id, datetime.now())

            try:
                comments = await self._provider.client.get_new_human_comments(
                    page_id, since
                )

                for comment in comments:
                    await self._emit_comment(page_id, comment)

                # Update timestamp
                self._comment_timestamps[page_id] = datetime.now()

            except Exception as e:
                logger.warning(f"Failed to check comments for page {page_id}: {e}")

    async def _emit_comment(self, page_id: str, comment: Any) -> None:
        """Emit a comment event.

        Args:
            page_id: Page ID
            comment: NotionComment object
        """
        if not self._handler:
            return

        # Create task ID
        task_id = TaskId(
            provider=ProviderType.NOTION,
            instance_id=self.database_id,
            external_id=page_id,
            identifier="",  # Will be resolved by orchestrator
        )

        # Check if bot comment
        bot_id = await self._provider.client.get_bot_user_id()
        is_bot = comment.created_by_id == bot_id

        event = TaskCommentAddedEvent(
            task_id=task_id,
            timestamp=comment.created_time,
            comment_body=comment.text,
            comment_author_id=comment.created_by_id or "",
            comment_author_name=None,
            is_bot_comment=is_bot,
            raw_data={"comment_id": comment.id},
        )

        logger.info(
            f"New comment on page {page_id}: "
            f"{comment.text[:50]}... ({'bot' if is_bot else 'human'})"
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

    async def trigger_existing_todo(self) -> None:
        """Trigger events for pages already in Todo status.

        Call this after initialization to start working on
        tasks that were moved to Todo before the poller started.
        """
        if not self._handler:
            return

        logger.info("Checking for existing Todo pages...")

        try:
            # Get instance for status mapping
            instance = self._instance

            # Determine the Todo status name
            todo_name = "Todo"
            mapping = instance.get_status_mapping()
            if mapping.get(TaskStatus.TODO):
                todo_name = mapping[TaskStatus.TODO]

            pages = await self._provider.client.query_pages(
                self.database_id,
                filter={
                    "property": "Status",
                    "status": {"equals": todo_name},
                },
            )

            for page in pages:
                logger.info(f"Triggering event for existing Todo page: {page.title}")
                await self._emit_status_change(page, "Backlog", todo_name)

        except Exception as e:
            logger.error(f"Failed to trigger existing Todo pages: {e}")
