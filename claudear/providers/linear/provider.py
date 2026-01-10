"""Linear provider implementation with multi-team support."""

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
from claudear.linear.client import LinearClient
from claudear.linear.labels import LabelManager, MajorStateLabel, ActivityLabel
from claudear.linear.models import Issue

logger = logging.getLogger(__name__)


# Map Linear workflow state types to unified TaskStatus
# Linear state types: "backlog", "unstarted", "started", "completed", "canceled"
STATE_TYPE_TO_STATUS: dict[str, TaskStatus] = {
    "backlog": TaskStatus.BACKLOG,
    "unstarted": TaskStatus.TODO,
    "started": TaskStatus.IN_PROGRESS,
    "completed": TaskStatus.DONE,
    "canceled": TaskStatus.DONE,  # Treat canceled as done
}

# Map unified TaskStatus to preferred Linear state type
STATUS_TO_STATE_TYPE: dict[TaskStatus, str] = {
    TaskStatus.BACKLOG: "backlog",
    TaskStatus.TODO: "unstarted",
    TaskStatus.IN_PROGRESS: "started",
    TaskStatus.IN_REVIEW: "started",  # Still in progress
    TaskStatus.DONE: "completed",
}


class LinearProvider(PMProvider):
    """Linear provider with multi-team support.

    Manages multiple Linear teams, each with its own:
    - Repository path
    - Label manager
    - Webhook event source

    Uses the state `type` field for consistent state detection across teams,
    avoiding the need for per-team state name configuration.
    """

    def __init__(self, api_key: str, labels_enabled: bool = True):
        """Initialize the Linear provider.

        Args:
            api_key: Linear API key
            labels_enabled: Whether to use Claudear labels
        """
        self._api_key = api_key
        self._labels_enabled = labels_enabled

        # Shared client (works across all teams with same API key)
        self._client = LinearClient(api_key)

        # Per-team resources
        self._instances: dict[str, ProviderInstance] = {}  # team_id -> instance
        self._label_managers: dict[str, LabelManager] = {}  # team_id -> manager
        self._event_sources: dict[str, "LinearWebhookEventSource"] = {}

        # Cache: state_id -> (name, type)
        self._state_cache: dict[str, tuple[str, str]] = {}

    @property
    def provider_type(self) -> ProviderType:
        return ProviderType.LINEAR

    @property
    def display_name(self) -> str:
        return "Linear"

    @property
    def client(self) -> LinearClient:
        """Get the underlying Linear client."""
        return self._client

    async def initialize(self) -> None:
        """Initialize the provider (validate credentials)."""
        # Validate API key by fetching bot user
        try:
            bot_id = await self._client.get_bot_user_id()
            logger.info(f"Linear provider initialized (bot user: {bot_id})")
        except Exception as e:
            logger.error(f"Failed to initialize Linear provider: {e}")
            raise

    async def initialize_instance(self, instance: ProviderInstance) -> None:
        """Initialize a specific team instance.

        Creates labels and caches workflow states for the team.

        Args:
            instance: Team configuration
        """
        team_id = instance.instance_id
        self._instances[team_id] = instance

        # Resolve team key to UUID
        team_uuid = await self._client.get_team_uuid(team_id)
        logger.info(f"Initializing Linear team: {team_id} (UUID: {team_uuid})")

        # Cache workflow states for this team
        states = await self._client.get_workflow_states(team_uuid)
        for state_name, state_id in states.items():
            # Query the state to get its type
            state_info = await self._get_state_info(state_id)
            if state_info:
                self._state_cache[state_id] = state_info

        # Initialize labels if enabled
        if self._labels_enabled:
            label_mgr = LabelManager(self._client, team_uuid)
            await label_mgr.initialize()
            self._label_managers[team_id] = label_mgr

        logger.info(f"Initialized team {team_id} with {len(states)} workflow states")

    async def shutdown(self) -> None:
        """Shutdown the provider."""
        # Stop all event sources
        for event_source in self._event_sources.values():
            await event_source.stop()
        logger.info("Linear provider shut down")

    async def _get_state_info(self, state_id: str) -> Optional[tuple[str, str]]:
        """Get state name and type by ID.

        Args:
            state_id: Workflow state ID

        Returns:
            Tuple of (name, type) or None if not found
        """
        if state_id in self._state_cache:
            return self._state_cache[state_id]

        # Query the state
        query = """
        query WorkflowState($id: String!) {
            workflowState(id: $id) {
                id
                name
                type
            }
        }
        """
        try:
            result = await self._client._query(query, {"id": state_id})
            state = result.get("workflowState")
            if state:
                info = (state["name"], state["type"])
                self._state_cache[state_id] = info
                return info
        except Exception as e:
            logger.warning(f"Failed to get state info for {state_id}: {e}")

        return None

    # -------------------------------------------------------------------------
    # Task Operations
    # -------------------------------------------------------------------------

    async def get_task(self, task_id: TaskId) -> Optional[UnifiedTask]:
        """Fetch a task by ID."""
        issue = await self._client.get_issue(task_id.external_id)
        if not issue:
            return None

        return self._issue_to_unified_task(issue, task_id.instance_id)

    def _issue_to_unified_task(
        self, issue: Issue, instance_id: str
    ) -> UnifiedTask:
        """Convert a Linear Issue to UnifiedTask."""
        # Determine status from state type
        status = TaskStatus.TODO
        if issue.state:
            state_type = issue.state.type
            status = STATE_TYPE_TO_STATUS.get(state_type, TaskStatus.TODO)

        task_id = TaskId(
            provider=ProviderType.LINEAR,
            instance_id=instance_id,
            external_id=issue.id,
            identifier=issue.identifier,
        )

        return UnifiedTask(
            id=task_id,
            title=issue.title,
            description=issue.description,
            status=status,
            created_at=issue.created_at,
            updated_at=issue.updated_at,
            extras={
                "priority": issue.priority,
                "assignee": issue.assignee.model_dump() if issue.assignee else None,
                "state_name": issue.state.name if issue.state else None,
                "state_type": issue.state.type if issue.state else None,
            },
        )

    async def update_task_status(
        self, task_id: TaskId, status: TaskStatus
    ) -> bool:
        """Update task status in Linear.

        Uses the state type to find the appropriate state in the team.
        """
        team_id = task_id.instance_id

        # Get team UUID
        team_uuid = await self._client.get_team_uuid(team_id)

        # Get workflow states for the team
        states = await self._client.get_workflow_states(team_uuid)

        # Find a state matching the target type
        target_type = STATUS_TO_STATE_TYPE.get(status, "started")
        target_state_name = None

        for state_name, state_id in states.items():
            state_info = await self._get_state_info(state_id)
            if state_info and state_info[1] == target_type:
                target_state_name = state_name
                break

        if not target_state_name:
            # Fall back to first state of the type or use instance config
            instance = self._instances.get(team_id)
            if instance:
                mapping = instance.get_status_mapping()
                target_state_name = mapping.get(status)

            if not target_state_name:
                logger.warning(
                    f"No state found for status {status} in team {team_id}"
                )
                return False

        return await self._client.update_issue_state(
            task_id.external_id, target_state_name, team_uuid
        )

    # -------------------------------------------------------------------------
    # Comments
    # -------------------------------------------------------------------------

    async def post_comment(self, task_id: TaskId, body: str) -> bool:
        """Post a comment on the task."""
        result = await self._client.post_comment(task_id.external_id, body)
        return result is not None

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
                "body": c.body,
                "author_id": c.user.id if c.user else "",
                "author_name": c.user.name if c.user else "",
                "created_at": c.created_at,
            }
            for c in comments
        ]

    # -------------------------------------------------------------------------
    # Activity Indicators
    # -------------------------------------------------------------------------

    async def set_working_indicator(
        self, task_id: TaskId, activity: Optional[str]
    ) -> None:
        """Set real-time activity indicator via labels."""
        if not self._labels_enabled:
            return

        label_mgr = self._label_managers.get(task_id.instance_id)
        if not label_mgr:
            return

        # Set major state to WORKING
        await label_mgr.set_major_state(task_id.external_id, MajorStateLabel.WORKING)

        # Map activity string to ActivityLabel
        if activity:
            activity_label = self._activity_string_to_label(activity)
            await label_mgr.set_activity(task_id.external_id, activity_label)
        else:
            await label_mgr.set_activity(task_id.external_id, None)

    def _activity_string_to_label(self, activity: str) -> ActivityLabel:
        """Map an activity description to an ActivityLabel."""
        activity_lower = activity.lower()
        if "read" in activity_lower:
            return ActivityLabel.READING
        elif "edit" in activity_lower or "writ" in activity_lower:
            return ActivityLabel.EDITING
        elif "test" in activity_lower or "run" in activity_lower:
            return ActivityLabel.TESTING
        elif "search" in activity_lower or "grep" in activity_lower or "glob" in activity_lower:
            return ActivityLabel.SEARCHING
        else:
            return ActivityLabel.THINKING

    async def set_blocked_indicator(
        self, task_id: TaskId, reason: Optional[str]
    ) -> None:
        """Indicate task is blocked."""
        if not self._labels_enabled:
            return

        label_mgr = self._label_managers.get(task_id.instance_id)
        if not label_mgr:
            return

        if reason:
            await label_mgr.set_major_state(task_id.external_id, MajorStateLabel.BLOCKED)
            await label_mgr.set_activity(task_id.external_id, None)
        else:
            # Clear blocked, set back to working
            await label_mgr.set_major_state(task_id.external_id, MajorStateLabel.WORKING)

    async def clear_indicators(self, task_id: TaskId) -> None:
        """Clear all status indicators."""
        if not self._labels_enabled:
            return

        label_mgr = self._label_managers.get(task_id.instance_id)
        if label_mgr:
            await label_mgr.clear_all_labels(task_id.external_id)

    # -------------------------------------------------------------------------
    # Branch / PR Tracking
    # -------------------------------------------------------------------------

    async def set_branch_info(
        self,
        task_id: TaskId,
        branch: str,
        pr_url: Optional[str] = None,
    ) -> None:
        """Store branch and PR info.

        Linear doesn't have native branch/PR fields, so we update labels.
        """
        if not self._labels_enabled:
            return

        label_mgr = self._label_managers.get(task_id.instance_id)
        if not label_mgr:
            return

        if pr_url:
            await label_mgr.set_major_state(task_id.external_id, MajorStateLabel.PR_READY)

    # -------------------------------------------------------------------------
    # Event Source
    # -------------------------------------------------------------------------

    def get_event_source(self, instance: ProviderInstance) -> EventSource:
        """Get the webhook event source for a team."""
        team_id = instance.instance_id
        if team_id not in self._event_sources:
            from claudear.providers.linear.webhook import LinearWebhookEventSource
            self._event_sources[team_id] = LinearWebhookEventSource(
                self, instance
            )
        return self._event_sources[team_id]

    # -------------------------------------------------------------------------
    # Status Mapping
    # -------------------------------------------------------------------------

    async def detect_status(
        self, task_id: TaskId, provider_status: str
    ) -> TaskStatus:
        """Map a Linear state ID to unified TaskStatus.

        Uses the state's `type` field for consistent detection.
        """
        state_info = await self._get_state_info(provider_status)
        if state_info:
            state_type = state_info[1]
            return STATE_TYPE_TO_STATUS.get(state_type, TaskStatus.TODO)
        return TaskStatus.TODO

    async def get_provider_status(
        self, task_id: TaskId, status: TaskStatus
    ) -> str:
        """Get the Linear state name for a TaskStatus.

        Returns the first matching state in the team by type.
        """
        team_id = task_id.instance_id
        team_uuid = await self._client.get_team_uuid(team_id)
        states = await self._client.get_workflow_states(team_uuid)

        target_type = STATUS_TO_STATE_TYPE.get(status, "started")

        for state_name, state_id in states.items():
            state_info = await self._get_state_info(state_id)
            if state_info and state_info[1] == target_type:
                return state_name

        # Fallback to instance config
        instance = self._instances.get(team_id)
        if instance:
            mapping = instance.get_status_mapping()
            if mapping.get(status):
                return mapping[status]

        # Ultimate fallback
        return status.value.replace("_", " ").title()
