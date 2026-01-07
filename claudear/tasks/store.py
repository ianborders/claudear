"""SQLite persistence for task state."""
from __future__ import annotations


import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

import aiosqlite

from claudear.tasks.state import TaskState

logger = logging.getLogger(__name__)


@dataclass
class TaskRecord:
    """Database record for a task."""

    issue_id: str
    issue_identifier: str
    title: str
    description: Optional[str]
    team_id: Optional[str]
    branch_name: str
    worktree_path: str
    state: TaskState
    blocked_reason: Optional[str]
    blocked_at: Optional[datetime]
    pr_number: Optional[int]
    pr_url: Optional[str]
    session_id: Optional[str]
    created_at: datetime
    updated_at: datetime


class TaskStore:
    """SQLite-based persistence for task records."""

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
            await db.execute("""
                CREATE TABLE IF NOT EXISTS tasks (
                    issue_id TEXT PRIMARY KEY,
                    issue_identifier TEXT NOT NULL,
                    title TEXT NOT NULL,
                    description TEXT,
                    team_id TEXT,
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
                CREATE INDEX IF NOT EXISTS idx_tasks_identifier
                ON tasks(issue_identifier)
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
                    issue_id, issue_identifier, title, description, team_id,
                    branch_name, worktree_path, state, blocked_reason, blocked_at,
                    pr_number, pr_url, session_id, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    task.issue_id,
                    task.issue_identifier,
                    task.title,
                    task.description,
                    task.team_id,
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

        logger.debug(f"Saved task {task.issue_identifier} in state {task.state.value}")

    async def get(self, issue_id: str) -> Optional[TaskRecord]:
        """Get a task by issue ID.

        Args:
            issue_id: Linear issue ID

        Returns:
            TaskRecord if found, None otherwise
        """
        await self.init()

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM tasks WHERE issue_id = ?", (issue_id,)
            )
            row = await cursor.fetchone()

            if row:
                return self._row_to_record(row)
            return None

    async def get_by_identifier(self, identifier: str) -> Optional[TaskRecord]:
        """Get a task by issue identifier (e.g., "ENG-123").

        Args:
            identifier: Issue identifier

        Returns:
            TaskRecord if found, None otherwise
        """
        await self.init()

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM tasks WHERE issue_identifier = ?", (identifier,)
            )
            row = await cursor.fetchone()

            if row:
                return self._row_to_record(row)
            return None

    async def get_by_state(self, state: TaskState) -> list[TaskRecord]:
        """Get all tasks in a specific state.

        Args:
            state: Task state to filter by

        Returns:
            List of matching task records
        """
        await self.init()

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM tasks WHERE state = ? ORDER BY updated_at DESC",
                (state.value,),
            )
            rows = await cursor.fetchall()
            return [self._row_to_record(row) for row in rows]

    async def get_blocked_tasks(self) -> list[TaskRecord]:
        """Get all blocked tasks.

        Returns:
            List of blocked task records
        """
        return await self.get_by_state(TaskState.BLOCKED)

    async def get_active_tasks(self) -> list[TaskRecord]:
        """Get all active (non-terminal) tasks.

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

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            placeholders = ",".join(["?"] * len(active_states))
            cursor = await db.execute(
                f"SELECT * FROM tasks WHERE state IN ({placeholders}) ORDER BY updated_at DESC",
                active_states,
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

    async def delete(self, issue_id: str) -> bool:
        """Delete a task record.

        Args:
            issue_id: Linear issue ID

        Returns:
            True if deleted, False if not found
        """
        await self.init()

        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "DELETE FROM tasks WHERE issue_id = ?", (issue_id,)
            )
            await db.commit()
            return cursor.rowcount > 0

    async def update_state(
        self,
        issue_id: str,
        state: TaskState,
        blocked_reason: Optional[str] = None,
    ) -> bool:
        """Update just the state of a task.

        Args:
            issue_id: Linear issue ID
            state: New state
            blocked_reason: Reason if blocked

        Returns:
            True if updated
        """
        await self.init()

        blocked_at = datetime.now().isoformat() if state == TaskState.BLOCKED else None

        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                """
                UPDATE tasks
                SET state = ?, blocked_reason = ?, blocked_at = ?, updated_at = ?
                WHERE issue_id = ?
            """,
                (
                    state.value,
                    blocked_reason,
                    blocked_at,
                    datetime.now().isoformat(),
                    issue_id,
                ),
            )
            await db.commit()
            return cursor.rowcount > 0

    async def update_pr_info(
        self, issue_id: str, pr_number: int, pr_url: str
    ) -> bool:
        """Update PR information for a task.

        Args:
            issue_id: Linear issue ID
            pr_number: GitHub PR number
            pr_url: GitHub PR URL

        Returns:
            True if updated
        """
        await self.init()

        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                """
                UPDATE tasks
                SET pr_number = ?, pr_url = ?, updated_at = ?
                WHERE issue_id = ?
            """,
                (pr_number, pr_url, datetime.now().isoformat(), issue_id),
            )
            await db.commit()
            return cursor.rowcount > 0

    async def update_session_id(self, issue_id: str, session_id: str) -> bool:
        """Update Claude session ID for a task.

        Args:
            issue_id: Linear issue ID
            session_id: Claude session ID

        Returns:
            True if updated
        """
        await self.init()

        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                """
                UPDATE tasks
                SET session_id = ?, updated_at = ?
                WHERE issue_id = ?
            """,
                (session_id, datetime.now().isoformat(), issue_id),
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
            issue_id=row["issue_id"],
            issue_identifier=row["issue_identifier"],
            title=row["title"],
            description=row["description"],
            team_id=row["team_id"],
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
