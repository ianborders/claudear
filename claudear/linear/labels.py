"""Label management for Linear issues."""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from claudear.linear.client import LinearClient

logger = logging.getLogger(__name__)


class MajorStateLabel(Enum):
    """Major state labels for Kanban visibility."""

    WORKING = "claudear:working"
    BLOCKED = "claudear:blocked"
    COMPLETED = "claudear:completed"
    PR_READY = "claudear:pr-ready"
    MERGING = "claudear:merging"
    MERGED = "claudear:merged"


class ActivityLabel(Enum):
    """Real-time activity labels."""

    READING = "claudear:reading"
    EDITING = "claudear:editing"
    TESTING = "claudear:testing"
    SEARCHING = "claudear:searching"
    THINKING = "claudear:thinking"


@dataclass
class LabelConfig:
    """Configuration for a label."""

    name: str
    color: str  # Hex without #
    description: str


# Default label configurations
MAJOR_STATE_LABELS: dict[MajorStateLabel, LabelConfig] = {
    MajorStateLabel.WORKING: LabelConfig(
        name="claudear:working",
        color="0066FF",  # Blue
        description="Claudear is actively working on this issue",
    ),
    MajorStateLabel.BLOCKED: LabelConfig(
        name="claudear:blocked",
        color="FF4444",  # Red
        description="Claudear needs human input to continue",
    ),
    MajorStateLabel.COMPLETED: LabelConfig(
        name="claudear:completed",
        color="9933FF",  # Purple
        description="Claudear has finished the implementation",
    ),
    MajorStateLabel.PR_READY: LabelConfig(
        name="claudear:pr-ready",
        color="00CC66",  # Green
        description="Claudear has created a PR for review",
    ),
    MajorStateLabel.MERGING: LabelConfig(
        name="claudear:merging",
        color="FF9900",  # Orange
        description="Claudear is merging the PR",
    ),
    MajorStateLabel.MERGED: LabelConfig(
        name="claudear:merged",
        color="00AA44",  # Darker green
        description="PR has been merged successfully",
    ),
}

ACTIVITY_LABELS: dict[ActivityLabel, LabelConfig] = {
    ActivityLabel.READING: LabelConfig(
        name="claudear:reading",
        color="9966FF",  # Purple
        description="Reading files",
    ),
    ActivityLabel.EDITING: LabelConfig(
        name="claudear:editing",
        color="FF9900",  # Orange
        description="Editing code",
    ),
    ActivityLabel.TESTING: LabelConfig(
        name="claudear:testing",
        color="00CCCC",  # Cyan
        description="Running tests",
    ),
    ActivityLabel.SEARCHING: LabelConfig(
        name="claudear:searching",
        color="FFCC00",  # Yellow
        description="Searching codebase",
    ),
    ActivityLabel.THINKING: LabelConfig(
        name="claudear:thinking",
        color="CCCCCC",  # Gray
        description="Analyzing/planning",
    ),
}


class LabelManager:
    """Manages Claudear labels on Linear issues."""

    def __init__(
        self,
        linear_client: "LinearClient",
        team_id: str,
        debounce_seconds: float = 2.0,
    ):
        """Initialize the label manager.

        Args:
            linear_client: Linear API client
            team_id: Linear team ID
            debounce_seconds: Minimum interval between activity label updates
        """
        self.client = linear_client
        self.team_id = team_id
        self.debounce_seconds = debounce_seconds

        # Label ID cache: label_name -> label_id
        self._label_ids: dict[str, str] = {}
        self._initialized = False

        # Track current labels per issue
        self._issue_major_labels: dict[str, Optional[MajorStateLabel]] = {}
        self._issue_activity_labels: dict[str, Optional[ActivityLabel]] = {}

        # Debouncing for activity labels - tracks (last_activity, last_update_timestamp)
        self._pending_activity: dict[str, tuple[Optional[ActivityLabel], float]] = {}

    async def initialize(self) -> None:
        """Ensure all Claudear labels exist in the team."""
        if self._initialized:
            return

        logger.info("Initializing Claudear labels...")

        # Resolve team key to UUID if needed
        team_uuid = await self.client.get_team_uuid(self.team_id)
        logger.debug(f"Resolved team '{self.team_id}' to UUID: {team_uuid}")

        # Create all labels
        all_labels: dict[MajorStateLabel | ActivityLabel, LabelConfig] = {
            **MAJOR_STATE_LABELS,
            **ACTIVITY_LABELS,
        }
        for label_enum, config in all_labels.items():
            label_id = await self.client.create_label(
                team_uuid,
                config.name,
                config.color,
                config.description,
            )
            self._label_ids[config.name] = label_id
            logger.debug(f"Label '{config.name}' ready: {label_id}")

        self._initialized = True
        logger.info(f"Initialized {len(self._label_ids)} Claudear labels")

    async def set_major_state(
        self, issue_id: str, state: Optional[MajorStateLabel]
    ) -> None:
        """Set the major state label for an issue.

        Removes ALL existing major state labels before setting the new one.
        Passing None removes all major state labels.

        Args:
            issue_id: Linear issue ID
            state: Major state to set, or None to clear
        """
        await self.initialize()

        # Remove ALL major state labels (not just the tracked one)
        for major_label in MajorStateLabel:
            config = MAJOR_STATE_LABELS[major_label]
            label_id = self._label_ids.get(config.name)
            if label_id:
                await self.client.remove_label_from_issue(issue_id, label_id, silent=True)

        # Add new label
        if state:
            new_config = MAJOR_STATE_LABELS[state]
            label_id = self._label_ids[new_config.name]
            try:
                await self.client.add_label_to_issue(issue_id, label_id)
                logger.info(f"Set {state.value} on {issue_id}")
            except Exception as e:
                logger.warning(f"Failed to add label {state.value}: {e}")

        self._issue_major_labels[issue_id] = state

    async def add_major_state(self, issue_id: str, state: MajorStateLabel) -> None:
        """Add a major state label without removing existing ones.

        Use this when you want multiple state labels visible (e.g., COMPLETED + PR_READY).

        Args:
            issue_id: Linear issue ID
            state: Major state to add
        """
        await self.initialize()

        new_config = MAJOR_STATE_LABELS[state]
        label_id = self._label_ids[new_config.name]
        try:
            await self.client.add_label_to_issue(issue_id, label_id)
            logger.info(f"Added {state.value} on {issue_id}")
        except Exception as e:
            logger.warning(f"Failed to add label {state.value}: {e}")

    async def set_activity(
        self, issue_id: str, activity: Optional[ActivityLabel]
    ) -> None:
        """Set the activity label for an issue (debounced).

        Only one activity label can be active at a time.
        Passing None removes all activity labels.
        First activity applies immediately, subsequent updates are debounced.

        Args:
            issue_id: Linear issue ID
            activity: Activity to set, or None to clear
        """
        await self.initialize()

        current = self._issue_activity_labels.get(issue_id)

        # Skip if no change
        if current == activity:
            return

        now = datetime.now().timestamp()

        # Check if we should debounce (skip if last update was recent)
        last_update = self._pending_activity.get(issue_id)
        if last_update and (now - last_update[1]) < self.debounce_seconds:
            # Update pending activity but don't apply yet
            self._pending_activity[issue_id] = (activity, last_update[1])
            return

        # Apply immediately
        try:
            # Remove current activity label
            if current:
                current_config = ACTIVITY_LABELS[current]
                label_id = self._label_ids[current_config.name]
                await self.client.remove_label_from_issue(issue_id, label_id, silent=True)

            # Add new activity label
            if activity:
                new_config = ACTIVITY_LABELS[activity]
                label_id = self._label_ids[new_config.name]
                await self.client.add_label_to_issue(issue_id, label_id)
                logger.info(f"Activity: {activity.value} on {issue_id}")

            self._issue_activity_labels[issue_id] = activity
            # Track when we last applied an update for debouncing
            self._pending_activity[issue_id] = (activity, now)
        except Exception as e:
            logger.warning(f"Failed to update activity label: {e}")


    async def clear_all_labels(self, issue_id: str) -> None:
        """Remove all Claudear labels from an issue.

        Args:
            issue_id: Linear issue ID
        """
        await self.initialize()

        # Get current labels on issue
        try:
            issue_labels = await self.client.get_issue_labels(issue_id)
        except Exception as e:
            logger.warning(f"Failed to get issue labels: {e}")
            issue_labels = []

        # Remove any that are ours
        for label_name, label_id in self._label_ids.items():
            if label_id in issue_labels:
                try:
                    await self.client.remove_label_from_issue(issue_id, label_id)
                except Exception as e:
                    logger.warning(f"Failed to remove label {label_name}: {e}")

        # Clear tracking
        self._issue_major_labels.pop(issue_id, None)
        self._issue_activity_labels.pop(issue_id, None)
        self._pending_activity.pop(issue_id, None)

        logger.info(f"Cleared all Claudear labels from {issue_id}")
