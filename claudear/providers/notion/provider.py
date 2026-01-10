"""Notion provider implementation with multi-database support."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional, Any

from claudear.core.types import (
    ProviderType,
    TaskId,
    TaskStatus,
    ProviderInstance,
    UnifiedTask,
)
from claudear.providers.base import PMProvider, EventSource
from claudear.providers.notion.client import NotionClient, NotionPage

logger = logging.getLogger(__name__)


# Map Notion status names to unified TaskStatus
# These are common defaults; per-database mappings can override
DEFAULT_STATUS_MAPPING: dict[str, TaskStatus] = {
    "backlog": TaskStatus.BACKLOG,
    "todo": TaskStatus.TODO,
    "to do": TaskStatus.TODO,
    "in progress": TaskStatus.IN_PROGRESS,
    "in review": TaskStatus.IN_REVIEW,
    "review": TaskStatus.IN_REVIEW,
    "done": TaskStatus.DONE,
    "complete": TaskStatus.DONE,
    "completed": TaskStatus.DONE,
}

# Map unified TaskStatus to Notion status names (defaults)
DEFAULT_REVERSE_MAPPING: dict[TaskStatus, str] = {
    TaskStatus.BACKLOG: "Backlog",
    TaskStatus.TODO: "Todo",
    TaskStatus.IN_PROGRESS: "In Progress",
    TaskStatus.IN_REVIEW: "In Review",
    TaskStatus.DONE: "Done",
}


class NotionProvider(PMProvider):
    """Notion provider with multi-database support.

    Manages multiple Notion databases, each with its own:
    - Repository path
    - Status property configuration
    - Polling event source

    Uses Notion's status/select property for task status tracking.
    """

    def __init__(self, api_key: str):
        """Initialize the Notion provider.

        Args:
            api_key: Notion integration API key
        """
        self._api_key = api_key

        # Shared client (works across all databases with same API key)
        self._client = NotionClient(api_key)

        # Per-database resources
        self._instances: dict[str, ProviderInstance] = {}  # database_id -> instance
        self._event_sources: dict[str, "NotionPollerEventSource"] = {}

        # ID generation counters per database
        self._id_counters: dict[str, int] = {}

    @property
    def provider_type(self) -> ProviderType:
        return ProviderType.NOTION

    @property
    def display_name(self) -> str:
        return "Notion"

    @property
    def client(self) -> NotionClient:
        """Get the underlying Notion client."""
        return self._client

    async def initialize(self) -> None:
        """Initialize the provider (validate credentials)."""
        try:
            bot_id = await self._client.get_bot_user_id()
            logger.info(f"Notion provider initialized (bot user: {bot_id})")
        except Exception as e:
            logger.error(f"Failed to initialize Notion provider: {e}")
            raise

    async def initialize_instance(self, instance: ProviderInstance) -> None:
        """Initialize a specific database instance.

        Validates the database exists and sets up property schema.

        Args:
            instance: Database configuration
        """
        database_id = instance.instance_id
        self._instances[database_id] = instance

        logger.info(f"Initializing Notion database: {database_id}")

        # Validate database exists and we have access
        try:
            db = await self._client.get_database(database_id)
            db_title = ""
            title_parts = db.get("title", [])
            if title_parts:
                db_title = title_parts[0].get("plain_text", "")
            logger.info(f"Connected to database: {db_title or database_id}")
        except Exception as e:
            logger.error(f"Failed to access database {database_id}: {e}")
            raise

        # Ensure required properties exist
        await self._ensure_properties(database_id)

        # Initialize ID counter
        await self._initialize_id_counter(database_id)

        logger.info(f"Initialized database {database_id}")

    async def _ensure_properties(self, database_id: str) -> None:
        """Ensure required Claudear properties exist in the database.

        Args:
            database_id: Database ID
        """
        db = await self._client.get_database(database_id)
        existing_props = db.get("properties", {})

        # Properties we need
        required_props = {
            "Claudear ID": {"rich_text": {}},
            "Branch": {"rich_text": {}},
            "PR URL": {"url": {}},
            "Current Status": {"rich_text": {}},
            "Blocked": {"checkbox": {}},
        }

        # Check which need to be created
        to_create = {}
        for name, schema in required_props.items():
            if name not in existing_props:
                logger.info(f"Creating property '{name}' in database {database_id}")
                to_create[name] = schema

        if to_create:
            await self._client.update_database_properties(database_id, to_create)
            logger.info(f"Created {len(to_create)} properties")

    async def _initialize_id_counter(self, database_id: str) -> None:
        """Initialize the ID counter by finding the max existing ID.

        Args:
            database_id: Database ID
        """
        pages = await self._client.query_pages(database_id)

        max_num = 0
        prefix = self._get_id_prefix(database_id)

        for page in pages:
            if page.claudear_id and page.claudear_id.startswith(prefix):
                try:
                    num = int(page.claudear_id.split("-")[-1])
                    max_num = max(max_num, num)
                except (IndexError, ValueError):
                    pass

        self._id_counters[database_id] = max_num
        logger.debug(f"ID counter for {database_id}: {max_num}")

    def _get_id_prefix(self, database_id: str) -> str:
        """Get the ID prefix for a database.

        Uses a short hash of the database ID for uniqueness.

        Args:
            database_id: Database ID

        Returns:
            ID prefix (e.g., "N-abc-")
        """
        # Use first 6 chars of database_id for prefix
        short_id = database_id.replace("-", "")[:6].upper()
        return f"N-{short_id}-"

    async def get_next_id(self, database_id: str) -> str:
        """Generate the next Claudear ID for a database.

        Args:
            database_id: Database ID

        Returns:
            Next ID (e.g., "N-ABC123-001")
        """
        counter = self._id_counters.get(database_id, 0) + 1
        self._id_counters[database_id] = counter
        prefix = self._get_id_prefix(database_id)
        return f"{prefix}{counter:03d}"

    async def shutdown(self) -> None:
        """Shutdown the provider."""
        # Stop all event sources
        for event_source in self._event_sources.values():
            await event_source.stop()

        # Close HTTP client
        await self._client.close()
        logger.info("Notion provider shut down")

    # -------------------------------------------------------------------------
    # Task Operations
    # -------------------------------------------------------------------------

    async def get_task(self, task_id: TaskId) -> Optional[UnifiedTask]:
        """Fetch a task by ID."""
        try:
            page = await self._client.get_page(task_id.external_id)
            return self._page_to_unified_task(page, task_id.instance_id)
        except Exception as e:
            logger.warning(f"Failed to get page {task_id.external_id}: {e}")
            return None

    def _page_to_unified_task(
        self, page: NotionPage, instance_id: str
    ) -> UnifiedTask:
        """Convert a Notion page to UnifiedTask."""
        # Determine status from page status property
        status = self._detect_status_from_name(page.status, instance_id)

        task_id = TaskId(
            provider=ProviderType.NOTION,
            instance_id=instance_id,
            external_id=page.id,
            identifier=page.claudear_id or page.id[:8],
        )

        return UnifiedTask(
            id=task_id,
            title=page.title,
            description=None,  # Notion page body requires separate API call
            status=status,
            created_at=page.created_time,
            updated_at=page.last_edited_time,
            extras={
                "status_name": page.status,
                "blocked": page.blocked,
                "current_status": page.current_status,
                "branch": page.branch,
                "pr_url": page.pr_url,
                "url": page.url,
            },
        )

    def _detect_status_from_name(
        self, status_name: Optional[str], instance_id: str
    ) -> TaskStatus:
        """Detect TaskStatus from a status name.

        Args:
            status_name: Notion status property value
            instance_id: Database ID for custom mappings

        Returns:
            Unified TaskStatus
        """
        if not status_name:
            return TaskStatus.TODO

        # Check instance-specific mapping first
        instance = self._instances.get(instance_id)
        if instance:
            mapping = instance.get_status_mapping()
            for unified_status, provider_status in mapping.items():
                if provider_status and provider_status.lower() == status_name.lower():
                    return unified_status

        # Fall back to default mapping
        return DEFAULT_STATUS_MAPPING.get(
            status_name.lower(), TaskStatus.TODO
        )

    async def update_task_status(
        self, task_id: TaskId, status: TaskStatus
    ) -> bool:
        """Update task status in Notion."""
        instance = self._instances.get(task_id.instance_id)

        # Get the Notion status name for this TaskStatus
        status_name = DEFAULT_REVERSE_MAPPING.get(status, "In Progress")

        # Check for instance-specific override
        if instance:
            mapping = instance.get_status_mapping()
            if mapping.get(status):
                status_name = mapping[status]

        try:
            await self._client.set_status(task_id.external_id, status_name)
            return True
        except Exception as e:
            logger.error(
                f"Failed to update status for {task_id.external_id}: {e}"
            )
            return False

    # -------------------------------------------------------------------------
    # Comments
    # -------------------------------------------------------------------------

    async def post_comment(self, task_id: TaskId, body: str) -> bool:
        """Post a comment on the task."""
        try:
            await self._client.add_comment(task_id.external_id, body)
            return True
        except Exception as e:
            logger.error(f"Failed to post comment: {e}")
            return False

    async def get_new_comments(
        self, task_id: TaskId, since: datetime
    ) -> list[dict[str, Any]]:
        """Get comments newer than the given timestamp."""
        comments = await self._client.get_new_human_comments(
            task_id.external_id, since
        )
        return [
            {
                "id": c.id,
                "body": c.text,
                "author_id": c.created_by_id or "",
                "author_name": "",  # Notion doesn't include name in comment
                "created_at": c.created_time,
            }
            for c in comments
        ]

    # -------------------------------------------------------------------------
    # Activity Indicators
    # -------------------------------------------------------------------------

    async def set_working_indicator(
        self, task_id: TaskId, activity: Optional[str]
    ) -> None:
        """Set real-time activity indicator via Current Status property."""
        try:
            await self._client.set_current_status(task_id.external_id, activity)
            await self._client.set_blocked(task_id.external_id, False)
        except Exception as e:
            logger.warning(f"Failed to set working indicator: {e}")

    async def set_blocked_indicator(
        self, task_id: TaskId, reason: Optional[str]
    ) -> None:
        """Indicate task is blocked."""
        try:
            if reason:
                await self._client.set_blocked(task_id.external_id, True)
                await self._client.set_current_status(
                    task_id.external_id, f"Blocked: {reason[:100]}"
                )
            else:
                await self._client.set_blocked(task_id.external_id, False)
                await self._client.set_current_status(task_id.external_id, None)
        except Exception as e:
            logger.warning(f"Failed to set blocked indicator: {e}")

    async def clear_indicators(self, task_id: TaskId) -> None:
        """Clear all status indicators from the task."""
        try:
            await self._client.set_current_status(task_id.external_id, None)
            await self._client.set_blocked(task_id.external_id, False)
        except Exception as e:
            logger.warning(f"Failed to clear indicators: {e}")

    # -------------------------------------------------------------------------
    # Branch / PR Tracking
    # -------------------------------------------------------------------------

    async def set_branch_info(
        self,
        task_id: TaskId,
        branch: str,
        pr_url: Optional[str] = None,
    ) -> None:
        """Store branch and PR information on the task."""
        try:
            await self._client.set_branch(task_id.external_id, branch)
            if pr_url:
                await self._client.set_pr_url(task_id.external_id, pr_url)
        except Exception as e:
            logger.warning(f"Failed to set branch info: {e}")

    # -------------------------------------------------------------------------
    # Event Source
    # -------------------------------------------------------------------------

    def get_event_source(self, instance: ProviderInstance) -> EventSource:
        """Get the polling event source for a database."""
        database_id = instance.instance_id
        if database_id not in self._event_sources:
            from claudear.providers.notion.poller import NotionPollerEventSource

            self._event_sources[database_id] = NotionPollerEventSource(
                self, instance
            )
        return self._event_sources[database_id]

    # -------------------------------------------------------------------------
    # Status Mapping
    # -------------------------------------------------------------------------

    async def detect_status(
        self, task_id: TaskId, provider_status: str
    ) -> TaskStatus:
        """Map a Notion status name to unified TaskStatus."""
        return self._detect_status_from_name(provider_status, task_id.instance_id)

    async def get_provider_status(
        self, task_id: TaskId, status: TaskStatus
    ) -> str:
        """Get the Notion status name for a TaskStatus."""
        instance = self._instances.get(task_id.instance_id)

        if instance:
            mapping = instance.get_status_mapping()
            if mapping.get(status):
                return mapping[status]

        return DEFAULT_REVERSE_MAPPING.get(status, "In Progress")

    # -------------------------------------------------------------------------
    # Notion-specific helpers
    # -------------------------------------------------------------------------

    async def assign_claudear_id(self, task_id: TaskId) -> str:
        """Assign a Claudear ID to a page if it doesn't have one.

        Args:
            task_id: Task identifier

        Returns:
            The assigned (or existing) Claudear ID
        """
        page = await self._client.get_page(task_id.external_id)
        if page.claudear_id:
            return page.claudear_id

        new_id = await self.get_next_id(task_id.instance_id)
        await self._client.set_claudear_id(task_id.external_id, new_id)
        return new_id
