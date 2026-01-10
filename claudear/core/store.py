"""SQLite persistence for multi-provider task state."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

import aiosqlite

from claudear.core.state import TaskState
from claudear.core.types import ProviderType, TaskId

logger = logging.getLogger(__name__)


@dataclass
class TaskRecord:
    """Database record for a task.

    Supports multi-provider, multi-instance storage with composite keys.
    """

    # Provider identification
    provider: ProviderType
    instance_id: str  # Team ID or Database ID
    external_id: str  # Provider's native UUID

    # Task identification
    task_identifier: str  # Human-readable: ENG-123, CLO-001

    # Task content
    title: str
    description: Optional[str]

    # Git/PR tracking
    branch_name: str
    worktree_path: str
    pr_number: Optional[int]
    pr_url: Optional[str]

    # State
    state: TaskState
    blocked_reason: Optional[str]
    blocked_at: Optional[datetime]

    # Claude session
    session_id: Optional[str]

    # Timestamps
    created_at: datetime
    updated_at: datetime

    @property
    def task_key(self) -> str:
        """Composite key for this task: 'provider:instance:external'."""
        return f"{self.provider.value}:{self.instance_id}:{self.external_id}"

    @property
    def instance_key(self) -> str:
        """Instance key: 'provider:instance'."""
        return f"{self.provider.value}:{self.instance_id}"

    @property
    def task_id(self) -> TaskId:
        """Get TaskId for this record."""
        return TaskId(
            provider=self.provider,
            instance_id=self.instance_id,
            external_id=self.external_id,
            identifier=self.task_identifier,
        )


class TaskStore:
    """SQLite-based persistence for multi-provider task records.

    Supports:
    - Multiple providers (Linear, Notion)
    - Multiple instances per provider (teams, databases)
    - Composite primary keys for task uniqueness
    """

    def __init__(self, db_path: str = "claudear.db"):
        """Initialize the task store.

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = Path(db_path)
        self._initialized = False

    async def init(self) -> None:
        """Initialize database schema."""
        if self._initialized:
            return

        async with aiosqlite.connect(self.db_path) as db:
            # Create tasks table with multi-provider support
            await db.execute("""
                CREATE TABLE IF NOT EXISTS tasks (
                    task_key TEXT PRIMARY KEY,
                    provider TEXT NOT NULL,
                    instance_id TEXT NOT NULL,
                    external_id TEXT NOT NULL,
                    task_identifier TEXT NOT NULL,
                    title TEXT NOT NULL,
                    description TEXT,
                    branch_name TEXT NOT NULL,
                    worktree_path TEXT NOT NULL,
                    state TEXT NOT NULL,
                    blocked_reason TEXT,
                    blocked_at TEXT,
                    pr_number INTEGER,
                    pr_url TEXT,
                    session_id TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)

            # Create indexes for common queries
            await db.execute("""
                CREATE INDEX IF NOT EXISTS idx_tasks_state
                ON tasks(state)
            """)
            await db.execute("""
                CREATE INDEX IF NOT EXISTS idx_tasks_provider
                ON tasks(provider)
            """)
            await db.execute("""
                CREATE INDEX IF NOT EXISTS idx_tasks_instance
                ON tasks(provider, instance_id)
            """)
            await db.execute("""
                CREATE INDEX IF NOT EXISTS idx_tasks_identifier
                ON tasks(task_identifier)
            """)

            await db.commit()

        self._initialized = True
        logger.info(f"Initialized task store at {self.db_path}")

    async def save(self, task: TaskRecord) -> None:
        """Save or update a task record.

        Args:
            task: Task record to save
        """
        await self.init()

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT OR REPLACE INTO tasks (
                    task_key, provider, instance_id, external_id, task_identifier,
                    title, description, branch_name, worktree_path,
                    state, blocked_reason, blocked_at,
                    pr_number, pr_url, session_id, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    task.task_key,
                    task.provider.value,
                    task.instance_id,
                    task.external_id,
                    task.task_identifier,
                    task.title,
                    task.description,
                    task.branch_name,
                    task.worktree_path,
                    task.state.value,
                    task.blocked_reason,
                    task.blocked_at.isoformat() if task.blocked_at else None,
                    task.pr_number,
                    task.pr_url,
                    task.session_id,
                    task.created_at.isoformat(),
                    datetime.now().isoformat(),
                ),
            )
            await db.commit()

        logger.debug(f"Saved task {task.task_identifier} in state {task.state.value}")

    async def get(
        self,
        provider_or_task_id: ProviderType | TaskId,
        instance_id: Optional[str] = None,
        external_id: Optional[str] = None,
    ) -> Optional[TaskRecord]:
        """Get a task by TaskId or by provider/instance/external ID.

        Can be called as:
            get(task_id)
            get(provider, instance_id, external_id)

        Args:
            provider_or_task_id: TaskId or ProviderType
            instance_id: Instance ID (if using separate args)
            external_id: External ID (if using separate args)

        Returns:
            TaskRecord if found, None otherwise
        """
        if isinstance(provider_or_task_id, TaskId):
            return await self.get_by_key(provider_or_task_id.composite_key)
        else:
            # Called with separate arguments
            if instance_id is None or external_id is None:
                raise ValueError("instance_id and external_id required when not using TaskId")
            task_key = f"{provider_or_task_id.value}:{instance_id}:{external_id}"
            return await self.get_by_key(task_key)

    async def get_by_key(self, task_key: str) -> Optional[TaskRecord]:
        """Get a task by composite key.

        Args:
            task_key: Composite key (provider:instance:external)

        Returns:
            TaskRecord if found, None otherwise
        """
        await self.init()

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM tasks WHERE task_key = ?", (task_key,)
            )
            row = await cursor.fetchone()

            if row:
                return self._row_to_record(row)
            return None

    async def get_by_external_id(
        self, provider: ProviderType, external_id: str
    ) -> Optional[TaskRecord]:
        """Get a task by provider and external ID.

        Useful when you have the provider's native ID but not the instance.

        Args:
            provider: Provider type
            external_id: Provider's native ID

        Returns:
            TaskRecord if found, None otherwise
        """
        await self.init()

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM tasks WHERE provider = ? AND external_id = ?",
                (provider.value, external_id),
            )
            row = await cursor.fetchone()

            if row:
                return self._row_to_record(row)
            return None

    async def get_by_identifier(self, identifier: str) -> Optional[TaskRecord]:
        """Get a task by human-readable identifier (e.g., "ENG-123").

        Args:
            identifier: Task identifier

        Returns:
            TaskRecord if found, None otherwise
        """
        await self.init()

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM tasks WHERE task_identifier = ?", (identifier,)
            )
            row = await cursor.fetchone()

            if row:
                return self._row_to_record(row)
            return None

    async def get_by_state(
        self,
        state: TaskState,
        provider: Optional[ProviderType] = None,
        instance_id: Optional[str] = None,
    ) -> list[TaskRecord]:
        """Get all tasks in a specific state.

        Args:
            state: Task state to filter by
            provider: Optional provider filter
            instance_id: Optional instance filter (requires provider)

        Returns:
            List of matching task records
        """
        await self.init()

        query = "SELECT * FROM tasks WHERE state = ?"
        params: list = [state.value]

        if provider:
            query += " AND provider = ?"
            params.append(provider.value)
            if instance_id:
                query += " AND instance_id = ?"
                params.append(instance_id)

        query += " ORDER BY updated_at DESC"

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(query, params)
            rows = await cursor.fetchall()
            return [self._row_to_record(row) for row in rows]

    async def get_blocked_tasks(
        self,
        provider: Optional[ProviderType] = None,
        instance_id: Optional[str] = None,
    ) -> list[TaskRecord]:
        """Get all blocked tasks.

        Args:
            provider: Optional provider filter
            instance_id: Optional instance filter

        Returns:
            List of blocked task records
        """
        return await self.get_by_state(TaskState.BLOCKED, provider, instance_id)

    async def get_active_tasks(
        self,
        provider: Optional[ProviderType] = None,
        instance_id: Optional[str] = None,
    ) -> list[TaskRecord]:
        """Get all active (non-terminal) tasks.

        Args:
            provider: Optional provider filter
            instance_id: Optional instance filter

        Returns:
            List of active task records
        """
        await self.init()

        active_states = [
            TaskState.PENDING.value,
            TaskState.IN_PROGRESS.value,
            TaskState.BLOCKED.value,
            TaskState.COMPLETED.value,
            TaskState.IN_REVIEW.value,
        ]

        query = f"SELECT * FROM tasks WHERE state IN ({','.join(['?'] * len(active_states))})"
        params: list = active_states.copy()

        if provider:
            query += " AND provider = ?"
            params.append(provider.value)
            if instance_id:
                query += " AND instance_id = ?"
                params.append(instance_id)

        query += " ORDER BY updated_at DESC"

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(query, params)
            rows = await cursor.fetchall()
            return [self._row_to_record(row) for row in rows]

    async def get_by_instance(
        self, provider: ProviderType, instance_id: str, limit: int = 100
    ) -> list[TaskRecord]:
        """Get all tasks for a specific instance.

        Args:
            provider: Provider type
            instance_id: Instance ID (team or database)
            limit: Maximum number of tasks

        Returns:
            List of task records
        """
        await self.init()

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                SELECT * FROM tasks
                WHERE provider = ? AND instance_id = ?
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (provider.value, instance_id, limit),
            )
            rows = await cursor.fetchall()
            return [self._row_to_record(row) for row in rows]

    async def get_all(self, limit: int = 100) -> list[TaskRecord]:
        """Get all tasks.

        Args:
            limit: Maximum number of tasks to return

        Returns:
            List of task records
        """
        await self.init()

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM tasks ORDER BY updated_at DESC LIMIT ?", (limit,)
            )
            rows = await cursor.fetchall()
            return [self._row_to_record(row) for row in rows]

    async def delete(self, task_id: TaskId) -> bool:
        """Delete a task record.

        Args:
            task_id: Task identifier

        Returns:
            True if deleted, False if not found
        """
        return await self.delete_by_key(task_id.composite_key)

    async def delete_by_key(self, task_key: str) -> bool:
        """Delete a task by composite key.

        Args:
            task_key: Composite key

        Returns:
            True if deleted, False if not found
        """
        await self.init()

        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "DELETE FROM tasks WHERE task_key = ?", (task_key,)
            )
            await db.commit()
            return cursor.rowcount > 0

    async def update_state(
        self,
        provider_or_task_id: ProviderType | TaskId,
        instance_id_or_state: str | TaskState,
        external_id_or_reason: Optional[str] = None,
        state: Optional[TaskState] = None,
        blocked_reason: Optional[str] = None,
    ) -> bool:
        """Update just the state of a task.

        Can be called as:
            update_state(task_id, state, blocked_reason)
            update_state(provider, instance_id, external_id, state, blocked_reason)

        Returns:
            True if updated
        """
        await self.init()

        # Parse arguments
        if isinstance(provider_or_task_id, TaskId):
            task_key = provider_or_task_id.composite_key
            actual_state = instance_id_or_state  # type: ignore
            actual_reason = external_id_or_reason
        else:
            if state is None:
                raise ValueError("state required when using separate arguments")
            task_key = f"{provider_or_task_id.value}:{instance_id_or_state}:{external_id_or_reason}"
            actual_state = state
            actual_reason = blocked_reason

        blocked_at = datetime.now().isoformat() if actual_state == TaskState.BLOCKED else None

        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                """
                UPDATE tasks
                SET state = ?, blocked_reason = ?, blocked_at = ?, updated_at = ?
                WHERE task_key = ?
            """,
                (
                    actual_state.value,
                    actual_reason,
                    blocked_at,
                    datetime.now().isoformat(),
                    task_key,
                ),
            )
            await db.commit()
            return cursor.rowcount > 0

    async def update_pr_info(
        self,
        provider_or_task_id: ProviderType | TaskId,
        instance_id_or_pr_number: str | int,
        external_id_or_pr_url: Optional[str] = None,
        pr_number: Optional[int] = None,
        pr_url: Optional[str] = None,
    ) -> bool:
        """Update PR information for a task.

        Can be called as:
            update_pr_info(task_id, pr_number, pr_url)
            update_pr_info(provider, instance_id, external_id, pr_number, pr_url)

        Returns:
            True if updated
        """
        await self.init()

        # Parse arguments
        if isinstance(provider_or_task_id, TaskId):
            task_key = provider_or_task_id.composite_key
            actual_pr_number = instance_id_or_pr_number  # type: ignore
            actual_pr_url = external_id_or_pr_url
        else:
            if pr_number is None or pr_url is None:
                raise ValueError("pr_number and pr_url required when using separate arguments")
            task_key = f"{provider_or_task_id.value}:{instance_id_or_pr_number}:{external_id_or_pr_url}"
            actual_pr_number = pr_number
            actual_pr_url = pr_url

        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                """
                UPDATE tasks
                SET pr_number = ?, pr_url = ?, updated_at = ?
                WHERE task_key = ?
            """,
                (actual_pr_number, actual_pr_url, datetime.now().isoformat(), task_key),
            )
            await db.commit()
            return cursor.rowcount > 0

    async def update_session_id(
        self,
        provider_or_task_id: ProviderType | TaskId,
        instance_id_or_session: str,
        external_id: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> bool:
        """Update Claude session ID for a task.

        Can be called as:
            update_session_id(task_id, session_id)
            update_session_id(provider, instance_id, external_id, session_id)

        Returns:
            True if updated
        """
        await self.init()

        # Parse arguments
        if isinstance(provider_or_task_id, TaskId):
            task_key = provider_or_task_id.composite_key
            actual_session_id = instance_id_or_session
        else:
            if session_id is None:
                raise ValueError("session_id required when using separate arguments")
            task_key = f"{provider_or_task_id.value}:{instance_id_or_session}:{external_id}"
            actual_session_id = session_id

        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                """
                UPDATE tasks
                SET session_id = ?, updated_at = ?
                WHERE task_key = ?
            """,
                (actual_session_id, datetime.now().isoformat(), task_key),
            )
            await db.commit()
            return cursor.rowcount > 0

    def _row_to_record(self, row: aiosqlite.Row) -> TaskRecord:
        """Convert a database row to a TaskRecord.

        Args:
            row: Database row

        Returns:
            TaskRecord instance
        """
        return TaskRecord(
            provider=ProviderType(row["provider"]),
            instance_id=row["instance_id"],
            external_id=row["external_id"],
            task_identifier=row["task_identifier"],
            title=row["title"],
            description=row["description"],
            branch_name=row["branch_name"],
            worktree_path=row["worktree_path"],
            state=TaskState(row["state"]),
            blocked_reason=row["blocked_reason"],
            blocked_at=(
                datetime.fromisoformat(row["blocked_at"])
                if row["blocked_at"]
                else None
            ),
            pr_number=row["pr_number"],
            pr_url=row["pr_url"],
            session_id=row["session_id"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )
