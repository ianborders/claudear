"""Task state machine for tracking task lifecycle.

This module is provider-agnostic and works with any PM system.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from claudear.core.types import TaskId


class TaskState(Enum):
    """Possible states for a task in the automation lifecycle.

    Note: This is the internal automation state, not the PM provider's state.
    """

    PENDING = "pending"  # Task queued, waiting to start
    IN_PROGRESS = "in_progress"  # Claude is actively working
    BLOCKED = "blocked"  # Claude needs human input
    FAILED = "failed"  # Task failed (terminal)
    COMPLETED = "completed"  # Claude finished work
    IN_REVIEW = "in_review"  # PR created, awaiting review
    DONE = "done"  # Merged and closed (terminal)


class InvalidTransitionError(Exception):
    """Raised when an invalid state transition is attempted."""

    def __init__(self, from_state: TaskState, to_state: TaskState):
        self.from_state = from_state
        self.to_state = to_state
        super().__init__(
            f"Invalid transition: {from_state.value} -> {to_state.value}"
        )


@dataclass
class StateTransition:
    """Record of a state transition."""

    from_state: TaskState
    to_state: TaskState
    timestamp: datetime
    reason: Optional[str] = None


class TaskStateMachine:
    """State machine for managing task lifecycle.

    Valid transitions:
        PENDING -> IN_PROGRESS
        IN_PROGRESS -> BLOCKED, COMPLETED, FAILED
        BLOCKED -> IN_PROGRESS, FAILED
        COMPLETED -> IN_REVIEW
        IN_REVIEW -> DONE, IN_PROGRESS (re-review)
        FAILED -> (terminal)
        DONE -> (terminal)
    """

    # Valid state transitions
    TRANSITIONS: dict[TaskState, set[TaskState]] = {
        TaskState.PENDING: {TaskState.IN_PROGRESS},
        TaskState.IN_PROGRESS: {
            TaskState.BLOCKED,
            TaskState.COMPLETED,
            TaskState.FAILED,
        },
        TaskState.BLOCKED: {TaskState.IN_PROGRESS, TaskState.FAILED},
        TaskState.COMPLETED: {TaskState.IN_REVIEW},
        TaskState.IN_REVIEW: {TaskState.DONE, TaskState.IN_PROGRESS},
        TaskState.FAILED: set(),  # Terminal state
        TaskState.DONE: set(),  # Terminal state
    }

    def __init__(self, initial_state: TaskState = TaskState.PENDING):
        """Initialize the state machine.

        Args:
            initial_state: Starting state (default: PENDING)
        """
        self._state = initial_state
        self._history: list[StateTransition] = []
        self._blocked_at: Optional[datetime] = None
        self._blocked_reason: Optional[str] = None

    @property
    def state(self) -> TaskState:
        """Get current state."""
        return self._state

    @property
    def history(self) -> list[StateTransition]:
        """Get state transition history."""
        return self._history.copy()

    @property
    def blocked_at(self) -> Optional[datetime]:
        """Get timestamp when task was blocked."""
        return self._blocked_at

    @property
    def blocked_reason(self) -> Optional[str]:
        """Get reason for blocking."""
        return self._blocked_reason

    @property
    def is_terminal(self) -> bool:
        """Check if current state is terminal."""
        return self._state in {TaskState.FAILED, TaskState.DONE}

    @property
    def is_active(self) -> bool:
        """Check if task is actively being worked on."""
        return self._state in {TaskState.IN_PROGRESS, TaskState.BLOCKED}

    def can_transition(self, to_state: TaskState) -> bool:
        """Check if a transition to the given state is valid.

        Args:
            to_state: Target state

        Returns:
            True if transition is valid
        """
        valid_targets = self.TRANSITIONS.get(self._state, set())
        return to_state in valid_targets

    def transition(
        self, to_state: TaskState, reason: Optional[str] = None
    ) -> None:
        """Transition to a new state.

        Args:
            to_state: Target state
            reason: Optional reason for transition

        Raises:
            InvalidTransitionError: If transition is not valid
        """
        if not self.can_transition(to_state):
            raise InvalidTransitionError(self._state, to_state)

        now = datetime.now()

        # Record transition
        transition = StateTransition(
            from_state=self._state,
            to_state=to_state,
            timestamp=now,
            reason=reason,
        )
        self._history.append(transition)

        # Update blocked tracking
        if to_state == TaskState.BLOCKED:
            self._blocked_at = now
            self._blocked_reason = reason
        elif self._state == TaskState.BLOCKED:
            # Leaving blocked state
            self._blocked_at = None
            self._blocked_reason = None

        self._state = to_state

    def start(self) -> None:
        """Start working on the task (PENDING -> IN_PROGRESS)."""
        self.transition(TaskState.IN_PROGRESS, "Task started")

    def block(self, reason: str) -> None:
        """Block the task waiting for input (IN_PROGRESS -> BLOCKED).

        Args:
            reason: Why the task is blocked
        """
        self.transition(TaskState.BLOCKED, reason)

    def unblock(self) -> None:
        """Unblock the task after receiving input (BLOCKED -> IN_PROGRESS)."""
        self.transition(TaskState.IN_PROGRESS, "Received input, resuming")

    def complete(self) -> None:
        """Mark task as completed (IN_PROGRESS -> COMPLETED)."""
        self.transition(TaskState.COMPLETED, "Task completed")

    def fail(self, reason: str) -> None:
        """Mark task as failed (-> FAILED).

        Args:
            reason: Why the task failed
        """
        self.transition(TaskState.FAILED, reason)

    def submit_for_review(self) -> None:
        """Submit for review (COMPLETED -> IN_REVIEW)."""
        self.transition(TaskState.IN_REVIEW, "PR created")

    def mark_done(self) -> None:
        """Mark as done (IN_REVIEW -> DONE)."""
        self.transition(TaskState.DONE, "Approved and merged")

    def request_changes(self) -> None:
        """Request changes (IN_REVIEW -> IN_PROGRESS)."""
        self.transition(TaskState.IN_PROGRESS, "Changes requested")

    def get_time_in_state(self) -> Optional[float]:
        """Get time spent in current state in seconds.

        Returns:
            Seconds in current state, or None if no history
        """
        if not self._history:
            return None

        last_transition = self._history[-1]
        return (datetime.now() - last_transition.timestamp).total_seconds()

    def get_blocked_duration(self) -> Optional[float]:
        """Get time blocked in seconds.

        Returns:
            Seconds blocked, or None if not blocked
        """
        if self._state != TaskState.BLOCKED or not self._blocked_at:
            return None
        return (datetime.now() - self._blocked_at).total_seconds()


@dataclass
class TaskContext:
    """Context information for an active task.

    This is the runtime representation of a task being worked on,
    containing both the task identity and operational state.
    """

    # Task identification (unified across providers)
    task_id: "TaskId"

    # Task content
    title: str
    description: Optional[str] = None

    # Git/PR tracking
    branch_name: Optional[str] = None
    worktree_path: Optional[str] = None
    pr_number: Optional[int] = None
    pr_url: Optional[str] = None

    # State machine
    state_machine: TaskStateMachine = field(default_factory=TaskStateMachine)

    # Timestamps
    created_at: datetime = field(default_factory=datetime.now)

    # Claude session tracking
    session_id: Optional[str] = None

    @property
    def state(self) -> TaskState:
        """Get current task state."""
        return self.state_machine.state

    @property
    def identifier(self) -> str:
        """Get human-readable task identifier."""
        return self.task_id.identifier

    @property
    def instance_key(self) -> str:
        """Get instance key for resource lookup."""
        return self.task_id.instance_key

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "provider": self.task_id.provider.value,
            "instance_id": self.task_id.instance_id,
            "external_id": self.task_id.external_id,
            "identifier": self.task_id.identifier,
            "title": self.title,
            "description": self.description,
            "branch_name": self.branch_name,
            "worktree_path": self.worktree_path,
            "pr_number": self.pr_number,
            "pr_url": self.pr_url,
            "state": self.state_machine.state.value,
            "blocked_reason": self.state_machine.blocked_reason,
            "blocked_at": (
                self.state_machine.blocked_at.isoformat()
                if self.state_machine.blocked_at
                else None
            ),
            "created_at": self.created_at.isoformat(),
            "session_id": self.session_id,
        }
