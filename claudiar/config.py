"""Configuration management for Claudiar."""

from pathlib import Path
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Linear Integration
    linear_api_key: str
    linear_webhook_secret: str
    linear_team_id: str

    # Linear Workflow States
    linear_state_todo: str = "Todo"
    linear_state_in_progress: str = "In Progress"
    linear_state_in_review: str = "In Review"
    linear_state_done: str = "Done"

    # GitHub
    github_token: str

    # Repository
    repo_path: str
    worktrees_dir: Optional[str] = None

    @property
    def worktrees_path(self) -> Path:
        """Get the worktrees directory path."""
        if self.worktrees_dir:
            return Path(self.worktrees_dir)
        return Path(self.repo_path) / ".worktrees"

    # Server
    webhook_port: int = 8000
    webhook_host: str = "0.0.0.0"

    # ngrok
    ngrok_authtoken: Optional[str] = None

    # Claude (uses Claude Code CLI, no API key needed)

    # Task Settings
    max_concurrent_tasks: int = 5
    comment_poll_interval: int = 30  # seconds
    blocked_timeout: int = 3600  # seconds (1 hour)

    # Logging
    log_level: str = "INFO"

    # Database
    db_path: str = "claudiar.db"


# Global settings instance - loaded lazily
_settings: Optional[Settings] = None


def get_settings() -> Settings:
    """Get the application settings, loading from environment if needed."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


def reload_settings() -> Settings:
    """Force reload settings from environment."""
    global _settings
    _settings = Settings()
    return _settings
