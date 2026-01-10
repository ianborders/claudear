"""Core abstractions for multi-provider task automation."""

from claudear.core.types import (
    ProviderType,
    TaskId,
    TaskStatus,
    ProviderInstance,
    UnifiedTask,
)
from claudear.core.state import (
    TaskState,
    TaskStateMachine,
    TaskContext,
    InvalidTransitionError,
    StateTransition,
)
from claudear.core.store import TaskStore, TaskRecord
from claudear.core.orchestrator import TaskOrchestrator

__all__ = [
    # Types
    "ProviderType",
    "TaskId",
    "TaskStatus",
    "ProviderInstance",
    "UnifiedTask",
    # State
    "TaskState",
    "TaskStateMachine",
    "TaskContext",
    "InvalidTransitionError",
    "StateTransition",
    # Store
    "TaskStore",
    "TaskRecord",
    # Orchestrator
    "TaskOrchestrator",
]
