"""Pydantic models for Linear API entities."""
from __future__ import annotations


from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class User(BaseModel):
    """Linear user model."""

    id: str
    name: str
    email: Optional[str] = None


class WorkflowState(BaseModel):
    """Linear workflow state model."""

    id: str
    name: str
    type: str  # "backlog", "unstarted", "started", "completed", "canceled"


class Team(BaseModel):
    """Linear team model."""

    id: str
    name: str
    key: str  # e.g., "ENG"


class Issue(BaseModel):
    """Linear issue model."""

    id: str
    identifier: str  # e.g., "ENG-123"
    title: str
    description: Optional[str] = None
    priority: int = 0
    state: Optional[WorkflowState] = None
    assignee: Optional[User] = None
    team: Optional[Team] = None
    created_at: Optional[datetime] = Field(None, alias="createdAt")
    updated_at: Optional[datetime] = Field(None, alias="updatedAt")

    class Config:
        populate_by_name = True


class Comment(BaseModel):
    """Linear comment model."""

    id: str
    body: str
    user: Optional[User] = None
    created_at: datetime = Field(alias="createdAt")

    class Config:
        populate_by_name = True


class IssueWebhook(BaseModel):
    """Issue data from webhook payload."""

    id: str
    identifier: str
    title: str
    description: Optional[str] = None
    priority: float = 0
    team_id: Optional[str] = Field(None, alias="teamId")

    class Config:
        populate_by_name = True


class WebhookPayload(BaseModel):
    """Linear webhook payload."""

    action: str  # "create", "update", "remove"
    type: str  # "Issue", "Comment", etc.
    data: dict[str, Any]
    updated_from: Optional[dict[str, Any]] = Field(None, alias="updatedFrom")
    url: Optional[str] = None
    created_at: datetime = Field(alias="createdAt")
    webhook_timestamp: Optional[int] = Field(None, alias="webhookTimestamp")

    class Config:
        populate_by_name = True

    def get_issue(self) -> Optional[IssueWebhook]:
        """Extract issue from webhook data if type is Issue."""
        if self.type == "Issue":
            return IssueWebhook(**self.data)
        return None

    def is_state_change(self) -> bool:
        """Check if this webhook represents a state change."""
        if self.action != "update" or not self.updated_from:
            return False
        return "stateId" in self.updated_from

    def get_previous_state_id(self) -> Optional[str]:
        """Get the previous state ID if this is a state change."""
        if self.updated_from:
            return self.updated_from.get("stateId")
        return None

    def get_new_state_id(self) -> Optional[str]:
        """Get the new state ID from issue data."""
        return self.data.get("stateId")
