"""Unified types for multi-provider task automation."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional, Any


class ProviderType(Enum):
    """Supported project management providers."""

    LINEAR = "linear"
    NOTION = "notion"
    # Future providers:
    # JIRA = "jira"
    # ASANA = "asana"
    # GITHUB_PROJECTS = "github_projects"


class TaskStatus(Enum):
    """Unified task status across all providers.

    Maps to provider-specific states:
    - Linear: workflow states (Todo, In Progress, etc.)
    - Notion: status property values
    """

    BACKLOG = "backlog"
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    IN_REVIEW = "in_review"
    DONE = "done"


@dataclass
class TaskId:
    """Unified task identifier across all provider instances.

    Uniquely identifies a task by combining:
    - provider: Which PM system (Linear, Notion, etc.)
    - instance_id: Which team/database within that provider
    - external_id: The provider's native ID (UUID)
    - identifier: Human-readable ID (ENG-123, CLO-001)
    """

    provider: ProviderType
    instance_id: str  # Team ID (ENG) or Database ID (abc123)
    external_id: str  # Linear issue UUID or Notion page UUID
    identifier: str  # Human-readable: "ENG-123" or "CLO-001"

    @property
    def composite_key(self) -> str:
        """Unique key for storage: 'linear:ENG:uuid' or 'notion:abc123:uuid'."""
        return f"{self.provider.value}:{self.instance_id}:{self.external_id}"

    @property
    def instance_key(self) -> str:
        """Key for looking up instance-specific resources: 'linear:ENG'."""
        return f"{self.provider.value}:{self.instance_id}"

    def __hash__(self) -> int:
        return hash(self.composite_key)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, TaskId):
            return False
        return self.composite_key == other.composite_key

    @classmethod
    def from_composite_key(
        cls, key: str, identifier: str = ""
    ) -> "TaskId":
        """Create TaskId from composite key string.

        Args:
            key: Composite key in format 'provider:instance:external'
            identifier: Human-readable identifier

        Returns:
            TaskId instance
        """
        parts = key.split(":", 2)
        if len(parts) != 3:
            raise ValueError(f"Invalid composite key format: {key}")
        return cls(
            provider=ProviderType(parts[0]),
            instance_id=parts[1],
            external_id=parts[2],
            identifier=identifier,
        )


@dataclass
class ProviderInstance:
    """Configuration for a specific team/database instance.

    Each instance represents one Linear team or one Notion database,
    with its own repository and optional status mappings.
    """

    provider: ProviderType
    instance_id: str  # Team ID (ENG) or Database ID (abc123)
    display_name: str  # "Engineering Team" or "Project Alpha"
    repo_path: Path  # Repository path for this team/database

    # Optional per-instance status mappings
    # If not set, provider will use default detection (e.g., Linear state type)
    status_backlog: Optional[str] = None
    status_todo: Optional[str] = None
    status_in_progress: Optional[str] = None
    status_in_review: Optional[str] = None
    status_done: Optional[str] = None

    @property
    def instance_key(self) -> str:
        """Key for looking up this instance: 'linear:ENG'."""
        return f"{self.provider.value}:{self.instance_id}"

    @property
    def worktrees_path(self) -> Path:
        """Default worktrees directory for this instance."""
        return self.repo_path / ".worktrees"

    def get_status_mapping(self) -> dict[TaskStatus, Optional[str]]:
        """Get status name mappings for this instance.

        Returns:
            Dict mapping TaskStatus to provider-specific status name
        """
        return {
            TaskStatus.BACKLOG: self.status_backlog,
            TaskStatus.TODO: self.status_todo,
            TaskStatus.IN_PROGRESS: self.status_in_progress,
            TaskStatus.IN_REVIEW: self.status_in_review,
            TaskStatus.DONE: self.status_done,
        }


@dataclass
class UnifiedTask:
    """Provider-agnostic task representation.

    Used for passing task data between components without
    coupling to provider-specific models.
    """

    id: TaskId
    title: str
    description: Optional[str] = None
    status: TaskStatus = TaskStatus.BACKLOG

    # Timestamps
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    # Work tracking
    branch_name: Optional[str] = None
    worktree_path: Optional[str] = None
    pr_number: Optional[int] = None
    pr_url: Optional[str] = None

    # Provider-specific extras (for passthrough data)
    extras: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "provider": self.id.provider.value,
            "instance_id": self.id.instance_id,
            "external_id": self.id.external_id,
            "identifier": self.id.identifier,
            "title": self.title,
            "description": self.description,
            "status": self.status.value,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "branch_name": self.branch_name,
            "worktree_path": self.worktree_path,
            "pr_number": self.pr_number,
            "pr_url": self.pr_url,
            "extras": self.extras,
        }
