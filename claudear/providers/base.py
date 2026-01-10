"""Abstract base classes for project management providers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from enum import Enum
from typing import Optional, Callable, Any, TYPE_CHECKING

if TYPE_CHECKING:
    from claudear.core.types import (
        TaskId,
        TaskStatus,
        ProviderInstance,
        UnifiedTask,
        ProviderType,
    )
    from claudear.events.types import Event


class EventSourceMode(Enum):
    """How the provider receives events."""

    WEBHOOK = "webhook"
    POLLING = "polling"


class EventSource(ABC):
    """Abstract base class for event sources.

    Event sources detect changes in the PM system (new tasks,
    status changes, comments) and emit events to handlers.
    """

    @property
    @abstractmethod
    def mode(self) -> EventSourceMode:
        """Return the event source mode (webhook or polling)."""
        pass

    @abstractmethod
    async def start(self) -> None:
        """Start receiving events.

        For webhooks: Register the webhook endpoint
        For polling: Start the polling loop
        """
        pass

    @abstractmethod
    async def stop(self) -> None:
        """Stop receiving events.

        For webhooks: Unregister (if applicable)
        For polling: Stop the polling loop
        """
        pass

    @abstractmethod
    def set_event_handler(
        self, handler: Callable[["Event"], Any]
    ) -> None:
        """Set the callback for received events.

        Args:
            handler: Async function called with each Event
        """
        pass


class PMProvider(ABC):
    """Abstract base class for project management providers.

    Each provider (Linear, Notion, Jira, etc.) implements this interface
    to integrate with the unified task automation system.

    A single provider may manage multiple instances (teams/databases).
    """

    @property
    @abstractmethod
    def provider_type(self) -> "ProviderType":
        """Return the provider type identifier."""
        pass

    @property
    @abstractmethod
    def display_name(self) -> str:
        """Human-readable name for logging (e.g., 'Linear', 'Notion')."""
        pass

    @abstractmethod
    async def initialize(self) -> None:
        """Initialize the provider.

        Called once on startup. Use for:
        - Validating API credentials
        - Creating required resources (labels, properties)
        - Setting up event sources
        """
        pass

    @abstractmethod
    async def initialize_instance(self, instance: "ProviderInstance") -> None:
        """Initialize a specific team/database instance.

        Called for each configured instance. Use for:
        - Validating instance exists
        - Creating instance-specific labels/properties
        - Caching workflow states

        Args:
            instance: Instance configuration
        """
        pass

    @abstractmethod
    async def shutdown(self) -> None:
        """Clean up provider resources.

        Called on shutdown. Stop event sources, close connections, etc.
        """
        pass

    # -------------------------------------------------------------------------
    # Task Operations
    # -------------------------------------------------------------------------

    @abstractmethod
    async def get_task(self, task_id: "TaskId") -> Optional["UnifiedTask"]:
        """Fetch a task by ID.

        Args:
            task_id: Unified task identifier

        Returns:
            UnifiedTask if found, None otherwise
        """
        pass

    @abstractmethod
    async def update_task_status(
        self, task_id: "TaskId", status: "TaskStatus"
    ) -> bool:
        """Update task status in the provider.

        Maps the unified TaskStatus to the provider-specific status.

        Args:
            task_id: Task identifier
            status: New unified status

        Returns:
            True if updated successfully
        """
        pass

    # -------------------------------------------------------------------------
    # Comments / Feedback
    # -------------------------------------------------------------------------

    @abstractmethod
    async def post_comment(self, task_id: "TaskId", body: str) -> bool:
        """Post a comment on the task.

        Used for progress updates, blocked notifications, etc.

        Args:
            task_id: Task identifier
            body: Comment text (may include markdown)

        Returns:
            True if posted successfully
        """
        pass

    @abstractmethod
    async def get_new_comments(
        self, task_id: "TaskId", since: datetime
    ) -> list[dict[str, Any]]:
        """Get comments newer than the given timestamp.

        Used for detecting human responses to blocked tasks.

        Args:
            task_id: Task identifier
            since: Only return comments after this time

        Returns:
            List of comment dicts with at least 'body' and 'author_id' keys
        """
        pass

    # -------------------------------------------------------------------------
    # Activity / Status Indicators
    # -------------------------------------------------------------------------

    @abstractmethod
    async def set_working_indicator(
        self, task_id: "TaskId", activity: Optional[str]
    ) -> None:
        """Set real-time activity indicator.

        Shows what Claude is currently doing (reading, editing, testing).

        For Linear: Updates activity labels
        For Notion: Updates status property

        Args:
            task_id: Task identifier
            activity: Activity description (e.g., "Reading files") or None to clear
        """
        pass

    @abstractmethod
    async def set_blocked_indicator(
        self, task_id: "TaskId", reason: Optional[str]
    ) -> None:
        """Indicate task is blocked waiting for input.

        Args:
            task_id: Task identifier
            reason: Why blocked, or None to clear blocked state
        """
        pass

    @abstractmethod
    async def clear_indicators(self, task_id: "TaskId") -> None:
        """Clear all status indicators from the task.

        Called when task is completed or cancelled.

        Args:
            task_id: Task identifier
        """
        pass

    # -------------------------------------------------------------------------
    # Branch / PR Tracking
    # -------------------------------------------------------------------------

    @abstractmethod
    async def set_branch_info(
        self,
        task_id: "TaskId",
        branch: str,
        pr_url: Optional[str] = None,
    ) -> None:
        """Store branch and PR information on the task.

        Args:
            task_id: Task identifier
            branch: Git branch name
            pr_url: GitHub PR URL if created
        """
        pass

    # -------------------------------------------------------------------------
    # Event Source
    # -------------------------------------------------------------------------

    @abstractmethod
    def get_event_source(self, instance: "ProviderInstance") -> EventSource:
        """Get the event source for an instance.

        Returns:
            EventSource for receiving events from this instance
        """
        pass

    # -------------------------------------------------------------------------
    # Status Mapping
    # -------------------------------------------------------------------------

    @abstractmethod
    async def detect_status(
        self, task_id: "TaskId", provider_status: str
    ) -> "TaskStatus":
        """Map a provider-specific status to unified TaskStatus.

        Used when receiving events to determine the unified status.

        Args:
            task_id: Task identifier (for instance-specific mappings)
            provider_status: The provider's native status value

        Returns:
            Unified TaskStatus
        """
        pass

    @abstractmethod
    async def get_provider_status(
        self, task_id: "TaskId", status: "TaskStatus"
    ) -> str:
        """Map a unified TaskStatus to provider-specific status.

        Args:
            task_id: Task identifier (for instance-specific mappings)
            status: Unified status

        Returns:
            Provider-specific status string
        """
        pass
