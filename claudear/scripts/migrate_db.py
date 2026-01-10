#!/usr/bin/env python3
"""Database migration script for Claudear multi-provider upgrade.

Migrates the old single-provider schema to the new multi-provider schema.

Old schema:
    - issue_id (primary key)
    - issue_identifier
    - team_id
    - ...

New schema:
    - task_key (primary key: provider:instance:external)
    - provider
    - instance_id
    - external_id
    - task_identifier
    - ...
"""

import asyncio
import logging
import sys
from datetime import datetime
from pathlib import Path

import aiosqlite

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


async def check_schema_version(db: aiosqlite.Connection) -> str:
    """Check which schema version the database has.

    Returns:
        'old' for Linear-only schema, 'new' for multi-provider schema, 'empty' for new db
    """
    cursor = await db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='tasks'"
    )
    if not await cursor.fetchone():
        return "empty"

    # Check if new schema columns exist
    cursor = await db.execute("PRAGMA table_info(tasks)")
    columns = {row[1] for row in await cursor.fetchall()}

    if "task_key" in columns and "provider" in columns:
        return "new"
    elif "issue_id" in columns:
        return "old"
    else:
        return "unknown"


async def migrate_to_multi_provider(
    db_path: Path,
    default_team_id: str = "DEFAULT",
    dry_run: bool = False,
) -> None:
    """Migrate old schema to new multi-provider schema.

    Args:
        db_path: Path to database file
        default_team_id: Default team ID for existing tasks
        dry_run: If True, don't actually make changes
    """
    logger.info(f"Migrating database: {db_path}")

    async with aiosqlite.connect(db_path) as db:
        schema_version = await check_schema_version(db)

        if schema_version == "empty":
            logger.info("Empty database, no migration needed")
            return

        if schema_version == "new":
            logger.info("Database already migrated to multi-provider schema")
            return

        if schema_version == "unknown":
            logger.error("Unknown database schema, cannot migrate")
            sys.exit(1)

        # Get existing tasks
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM tasks")
        old_tasks = await cursor.fetchall()

        logger.info(f"Found {len(old_tasks)} tasks to migrate")

        if dry_run:
            logger.info("[DRY RUN] Would migrate the following tasks:")
            for task in old_tasks:
                team_id = task["team_id"] or default_team_id
                task_key = f"linear:{team_id}:{task['issue_id']}"
                logger.info(f"  {task['issue_identifier']} -> {task_key}")
            return

        # Create backup
        backup_path = db_path.with_suffix(".db.backup")
        if not backup_path.exists():
            logger.info(f"Creating backup at {backup_path}")
            import shutil

            shutil.copy(db_path, backup_path)

        # Rename old table
        await db.execute("ALTER TABLE tasks RENAME TO tasks_old")

        # Create new table
        await db.execute("""
            CREATE TABLE tasks (
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

        # Create indexes
        await db.execute("""
            CREATE INDEX idx_tasks_state ON tasks(state)
        """)
        await db.execute("""
            CREATE INDEX idx_tasks_provider ON tasks(provider)
        """)
        await db.execute("""
            CREATE INDEX idx_tasks_instance ON tasks(provider, instance_id)
        """)
        await db.execute("""
            CREATE INDEX idx_tasks_identifier ON tasks(task_identifier)
        """)

        # Migrate data
        for task in old_tasks:
            team_id = task["team_id"] or default_team_id
            task_key = f"linear:{team_id}:{task['issue_id']}"

            await db.execute(
                """
                INSERT INTO tasks (
                    task_key, provider, instance_id, external_id, task_identifier,
                    title, description, branch_name, worktree_path,
                    state, blocked_reason, blocked_at,
                    pr_number, pr_url, session_id, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    task_key,
                    "linear",  # All old tasks were Linear
                    team_id,
                    task["issue_id"],  # external_id = issue_id
                    task["issue_identifier"],  # task_identifier = issue_identifier
                    task["title"],
                    task["description"],
                    task["branch_name"],
                    task["worktree_path"],
                    task["state"],
                    task["blocked_reason"],
                    task["blocked_at"],
                    task["pr_number"],
                    task["pr_url"],
                    task["session_id"],
                    task["created_at"],
                    datetime.now().isoformat(),
                ),
            )

        # Drop old table
        await db.execute("DROP TABLE tasks_old")

        await db.commit()

        logger.info(f"Successfully migrated {len(old_tasks)} tasks")
        logger.info(f"Backup saved at {backup_path}")


async def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Migrate Claudear database to multi-provider schema"
    )
    parser.add_argument(
        "db_path",
        type=Path,
        nargs="?",
        default=Path("claudear.db"),
        help="Path to database file (default: claudear.db)",
    )
    parser.add_argument(
        "--team-id",
        default="DEFAULT",
        help="Default team ID for tasks without team_id",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be migrated without making changes",
    )

    args = parser.parse_args()

    if not args.db_path.exists():
        logger.error(f"Database not found: {args.db_path}")
        sys.exit(1)

    await migrate_to_multi_provider(
        args.db_path,
        default_team_id=args.team_id,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    asyncio.run(main())
