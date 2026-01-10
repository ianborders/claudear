"""Multi-provider configuration for Claudear."""

from __future__ import annotations

import os
import logging
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, field

from pydantic_settings import BaseSettings, SettingsConfigDict

from claudear.core.types import ProviderType, TaskStatus, ProviderInstance

logger = logging.getLogger(__name__)


def _find_env_file() -> Optional[str]:
    """Find .env file in current working directory."""
    env_path = Path.cwd() / ".env"
    if env_path.exists():
        return str(env_path)
    return None


class MultiProviderSettings(BaseSettings):
    """Settings for multi-provider task automation.

    Supports both single-team/database backward-compatible configuration
    and multi-team/database configurations.

    Configuration priority:
    1. Explicit multi-instance vars (LINEAR_TEAM_IDS, NOTION_DATABASE_IDS)
    2. Single-instance vars for backward compatibility (LINEAR_TEAM_ID)
    """

    model_config = SettingsConfigDict(
        env_file=_find_env_file(),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # -------------------------------------------------------------------------
    # Linear Configuration
    # -------------------------------------------------------------------------

    # API credentials (optional - only if using Linear)
    linear_api_key: Optional[str] = None
    linear_webhook_secret: Optional[str] = None

    # Multi-team: comma-separated team keys (e.g., "ENG,INFRA,DESIGN")
    linear_team_ids: Optional[str] = None
    # Single-team (backward compat)
    linear_team_id: Optional[str] = None

    # Linear labels
    linear_labels_enabled: bool = True
    linear_labels_activity_enabled: bool = True
    linear_labels_debounce_seconds: float = 2.0

    # -------------------------------------------------------------------------
    # Notion Configuration
    # -------------------------------------------------------------------------

    # API credentials (optional - only if using Notion)
    notion_api_key: Optional[str] = None

    # Multi-database: comma-separated database IDs
    notion_database_ids: Optional[str] = None
    # Single-database (backward compat)
    notion_database_id: Optional[str] = None

    # Notion polling
    notion_poll_interval: int = 5  # seconds

    # -------------------------------------------------------------------------
    # Shared Configuration
    # -------------------------------------------------------------------------

    # GitHub
    github_token: Optional[str] = None

    # Default repo path (for single-instance backward compat)
    repo_path: Optional[str] = None
    worktrees_dir: Optional[str] = None

    # Server
    webhook_port: int = 8000
    webhook_host: str = "0.0.0.0"
    ngrok_authtoken: Optional[str] = None

    # Task settings
    max_concurrent_tasks: int = 5
    comment_poll_interval: int = 30  # seconds
    blocked_timeout: int = 3600  # seconds

    # Logging
    log_level: str = "INFO"

    # Database
    db_path: str = "claudear.db"

    # -------------------------------------------------------------------------
    # Instance Resolution
    # -------------------------------------------------------------------------

    def get_linear_team_ids(self) -> list[str]:
        """Get list of Linear team IDs/keys to manage.

        Returns:
            List of team keys (may be empty if Linear not configured)
        """
        if self.linear_team_ids:
            return [t.strip() for t in self.linear_team_ids.split(",") if t.strip()]
        elif self.linear_team_id:
            return [self.linear_team_id]
        return []

    def get_notion_database_ids(self) -> list[str]:
        """Get list of Notion database IDs to manage.

        Returns:
            List of database IDs (may be empty if Notion not configured)
        """
        if self.notion_database_ids:
            return [d.strip() for d in self.notion_database_ids.split(",") if d.strip()]
        elif self.notion_database_id:
            return [self.notion_database_id]
        return []

    def get_instance_repo_path(
        self, provider: ProviderType, instance_id: str
    ) -> Optional[Path]:
        """Get the repository path for a specific instance.

        Looks for environment variables in order:
        1. LINEAR_<TEAM>_REPO or NOTION_<DB>_REPO (exact match)
        2. Default repo_path (if only one instance configured)

        Args:
            provider: Provider type
            instance_id: Team key or database ID

        Returns:
            Repository path or None if not configured
        """
        # Build environment variable name
        safe_id = instance_id.replace("-", "_").upper()

        if provider == ProviderType.LINEAR:
            env_var = f"LINEAR_{safe_id}_REPO"
        else:
            env_var = f"NOTION_{safe_id}_REPO"

        # Check for instance-specific path
        repo = os.environ.get(env_var)
        if repo:
            return Path(repo)

        # Fall back to default repo_path for single-instance setups
        if self.repo_path:
            # Only use default if there's a single instance of this provider
            if provider == ProviderType.LINEAR:
                teams = self.get_linear_team_ids()
                if len(teams) == 1:
                    return Path(self.repo_path)
            else:
                dbs = self.get_notion_database_ids()
                if len(dbs) == 1:
                    return Path(self.repo_path)

        return None

    def get_linear_instance(self, team_id: str) -> Optional[ProviderInstance]:
        """Create a ProviderInstance for a Linear team.

        Args:
            team_id: Team key (e.g., "ENG")

        Returns:
            ProviderInstance or None if repo not configured
        """
        repo_path = self.get_instance_repo_path(ProviderType.LINEAR, team_id)
        if not repo_path:
            logger.warning(f"No repo configured for Linear team {team_id}")
            return None

        # Get optional status mappings from environment
        status_mapping = self._get_status_mapping(ProviderType.LINEAR, team_id)

        return ProviderInstance(
            provider=ProviderType.LINEAR,
            instance_id=team_id,
            display_name=f"Linear/{team_id}",
            repo_path=repo_path,
            status_todo=status_mapping.get(TaskStatus.TODO),
            status_in_progress=status_mapping.get(TaskStatus.IN_PROGRESS),
            status_in_review=status_mapping.get(TaskStatus.IN_REVIEW),
            status_done=status_mapping.get(TaskStatus.DONE),
        )

    def get_notion_instance(self, database_id: str) -> Optional[ProviderInstance]:
        """Create a ProviderInstance for a Notion database.

        Args:
            database_id: Database ID

        Returns:
            ProviderInstance or None if repo not configured
        """
        repo_path = self.get_instance_repo_path(ProviderType.NOTION, database_id)
        if not repo_path:
            logger.warning(f"No repo configured for Notion database {database_id}")
            return None

        # Use short ID for display
        short_id = database_id.replace("-", "")[:8]
        status_mapping = self._get_status_mapping(ProviderType.NOTION, database_id)

        return ProviderInstance(
            provider=ProviderType.NOTION,
            instance_id=database_id,
            display_name=f"Notion/{short_id}",
            repo_path=repo_path,
            status_todo=status_mapping.get(TaskStatus.TODO),
            status_in_progress=status_mapping.get(TaskStatus.IN_PROGRESS),
            status_in_review=status_mapping.get(TaskStatus.IN_REVIEW),
            status_done=status_mapping.get(TaskStatus.DONE),
        )

    def _get_status_mapping(
        self, provider: ProviderType, instance_id: str
    ) -> dict[TaskStatus, str]:
        """Get custom status mappings for an instance.

        Looks for environment variables like:
        - LINEAR_ENG_STATE_TODO=Ready
        - NOTION_abc123_STATUS_TODO=Next

        Args:
            provider: Provider type
            instance_id: Instance ID

        Returns:
            Mapping of TaskStatus to provider status names
        """
        safe_id = instance_id.replace("-", "_").upper()

        if provider == ProviderType.LINEAR:
            prefix = f"LINEAR_{safe_id}_STATE_"
        else:
            prefix = f"NOTION_{safe_id}_STATUS_"

        mapping = {}
        status_map = {
            "TODO": TaskStatus.TODO,
            "IN_PROGRESS": TaskStatus.IN_PROGRESS,
            "IN_REVIEW": TaskStatus.IN_REVIEW,
            "DONE": TaskStatus.DONE,
        }

        for status_name, status_enum in status_map.items():
            env_var = f"{prefix}{status_name}"
            value = os.environ.get(env_var)
            if value:
                mapping[status_enum] = value

        return mapping

    def has_linear(self) -> bool:
        """Check if Linear is configured."""
        return bool(self.linear_api_key and self.get_linear_team_ids())

    def has_notion(self) -> bool:
        """Check if Notion is configured."""
        return bool(self.notion_api_key and self.get_notion_database_ids())

    def validate(self) -> list[str]:
        """Validate the configuration.

        Returns:
            List of validation error messages (empty if valid)
        """
        errors = []

        # At least one provider must be configured
        if not self.has_linear() and not self.has_notion():
            errors.append(
                "No providers configured. Set LINEAR_API_KEY + LINEAR_TEAM_ID "
                "or NOTION_API_KEY + NOTION_DATABASE_ID"
            )

        # Linear validation
        if self.linear_api_key:
            if not self.get_linear_team_ids():
                errors.append(
                    "LINEAR_API_KEY set but no teams configured. "
                    "Set LINEAR_TEAM_ID or LINEAR_TEAM_IDS"
                )
            if not self.linear_webhook_secret:
                errors.append(
                    "LINEAR_API_KEY set but LINEAR_WEBHOOK_SECRET missing"
                )

            # Check each team has a repo
            for team_id in self.get_linear_team_ids():
                if not self.get_instance_repo_path(ProviderType.LINEAR, team_id):
                    safe_id = team_id.replace("-", "_").upper()
                    errors.append(
                        f"No repository configured for Linear team {team_id}. "
                        f"Set LINEAR_{safe_id}_REPO or REPO_PATH"
                    )

        # Notion validation
        if self.notion_api_key:
            if not self.get_notion_database_ids():
                errors.append(
                    "NOTION_API_KEY set but no databases configured. "
                    "Set NOTION_DATABASE_ID or NOTION_DATABASE_IDS"
                )

            # Check each database has a repo
            for db_id in self.get_notion_database_ids():
                if not self.get_instance_repo_path(ProviderType.NOTION, db_id):
                    safe_id = db_id.replace("-", "_").upper()
                    errors.append(
                        f"No repository configured for Notion database {db_id}. "
                        f"Set NOTION_{safe_id}_REPO or REPO_PATH"
                    )

        # GitHub token needed for PR operations
        if not self.github_token:
            errors.append("GITHUB_TOKEN not set")

        return errors


# Global settings instance
_settings: Optional[MultiProviderSettings] = None


def get_settings() -> MultiProviderSettings:
    """Get the application settings."""
    global _settings
    if _settings is None:
        _settings = MultiProviderSettings()
    return _settings


def reload_settings() -> MultiProviderSettings:
    """Force reload settings from environment."""
    global _settings
    _settings = MultiProviderSettings()
    return _settings
