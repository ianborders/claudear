"""Event types for provider notifications."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, Any

from claudear.core.types import TaskId, TaskStatus


class EventType(Enum):
    """Types of events from providers."""

    TASK_STATUS_CHANGED = "task_status_changed"
    TASK_COMMENT_ADDED = "task_comment_added"
    TASK_UPDATED = "task_updated"


@dataclass
class Event:
    """Base event from a provider.

    All events include the task identifier and timestamp.
    """

    type: EventType
    task_id: TaskId
    timestamp: datetime = field(default_factory=datetime.now)

    # Raw provider data for debugging/passthrough
    raw_data: Optional[dict[str, Any]] = None


@dataclass
class TaskStatusChangedEvent(Event):
    """Event when a task status changes.

    This is the primary trigger for task automation:
    - Task moved to "Todo" -> Start working
    - Task moved to "Done" -> Merge PR and cleanup
    """

    type: EventType = field(default=EventType.TASK_STATUS_CHANGED, init=False)

    # Status change details
    old_status: Optional[TaskStatus] = None
    new_status: TaskStatus = TaskStatus.TODO

    # Task content (for starting new tasks)
    task_title: str = ""
    task_description: Optional[str] = None

    def is_transition_to_todo(self) -> bool:
        """Check if this is a transition to TODO status."""
        return self.new_status == TaskStatus.TODO

    def is_transition_to_done(self) -> bool:
        """Check if this is a transition to DONE status."""
        return self.new_status == TaskStatus.DONE

    def is_transition_to_in_progress(self) -> bool:
        """Check if this is a transition to IN_PROGRESS status."""
        return self.new_status == TaskStatus.IN_PROGRESS


@dataclass
class TaskCommentAddedEvent(Event):
    """Event when a comment is added to a task.

    Used to detect human responses for unblocking tasks.
    """

    type: EventType = field(default=EventType.TASK_COMMENT_ADDED, init=False)

    # Comment details
    comment_body: str = ""
    comment_author_id: str = ""
    comment_author_name: Optional[str] = None

    # Whether this is from the automation bot
    is_bot_comment: bool = False

    def is_human_comment(self) -> bool:
        """Check if this is a human (non-bot) comment."""
        return not self.is_bot_comment


@dataclass
class TaskUpdatedEvent(Event):
    """Event when a task is updated (title, description, etc.).

    This is a general update event for non-status changes.
    """

    type: EventType = field(default=EventType.TASK_UPDATED, init=False)

    # What was updated
    updated_fields: list[str] = field(default_factory=list)

    # New values (if relevant)
    new_title: Optional[str] = None
    new_description: Optional[str] = None
