"""Git worktree management for parallel task isolation."""
from __future__ import annotations


import asyncio
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class WorktreeError(Exception):
    """Error during worktree operations."""

    pass


@dataclass
class Worktree:
    """Represents a git worktree."""

    path: Path
    branch: str
    commit: Optional[str] = None
    is_main: bool = False


class WorktreeManager:
    """Manages git worktrees for parallel task execution."""

    def __init__(self, repo_path: str, worktrees_dir: Optional[Path] = None):
        """Initialize the worktree manager.

        Args:
            repo_path: Path to the main git repository
            worktrees_dir: Directory to create worktrees in (default: repo/.worktrees)
        """
        self.repo_path = Path(repo_path)
        self.worktrees_dir = worktrees_dir or (self.repo_path / ".worktrees")

        if not self.repo_path.exists():
            raise WorktreeError(f"Repository path does not exist: {repo_path}")

        # Ensure worktrees directory exists
        self.worktrees_dir.mkdir(parents=True, exist_ok=True)

    async def _run_git(
        self, *args: str, cwd: Optional[Path] = None, check: bool = True
    ) -> str:
        """Run a git command.

        Args:
            *args: Git command arguments
            cwd: Working directory (default: repo_path)
            check: Raise exception on non-zero exit

        Returns:
            Command stdout

        Raises:
            WorktreeError: If command fails and check=True
        """
        process = await asyncio.create_subprocess_exec(
            "git",
            *args,
            cwd=cwd or self.repo_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()

        if check and process.returncode != 0:
            error_msg = stderr.decode().strip() or stdout.decode().strip()
            raise WorktreeError(f"Git command failed: git {' '.join(args)}\n{error_msg}")

        return stdout.decode().strip()

    def _sanitize_name(self, identifier: str) -> str:
        """Sanitize an issue identifier for use as directory/branch name.

        Args:
            identifier: Issue identifier (e.g., "ENG-123")

        Returns:
            Sanitized name safe for filesystem and git
        """
        # Replace problematic characters
        sanitized = re.sub(r"[^a-zA-Z0-9\-_]", "-", identifier)
        # Remove multiple consecutive dashes
        sanitized = re.sub(r"-+", "-", sanitized)
        # Remove leading/trailing dashes
        sanitized = sanitized.strip("-")
        return sanitized.lower()

    async def create(
        self,
        issue_identifier: str,
        base_branch: str = "main",
        setup_command: Optional[str] = None,
    ) -> Path:
        """Create a new worktree for an issue.

        Args:
            issue_identifier: Issue identifier (e.g., "ENG-123")
            base_branch: Base branch to create from (default: "main")
            setup_command: Optional command to run after creation (e.g., "npm install")

        Returns:
            Path to the created worktree

        Raises:
            WorktreeError: If worktree creation fails
        """
        safe_name = self._sanitize_name(issue_identifier)
        branch_name = f"claudear/{safe_name}"
        worktree_path = self.worktrees_dir / safe_name

        # Check if worktree already exists
        if worktree_path.exists():
            logger.warning(f"Worktree already exists at {worktree_path}")
            return worktree_path

        logger.info(f"Creating worktree for {issue_identifier} at {worktree_path}")

        try:
            # Fetch latest from remote
            await self._run_git("fetch", "origin", base_branch)

            # Create worktree with new branch from origin/base_branch
            await self._run_git(
                "worktree",
                "add",
                "-b",
                branch_name,
                str(worktree_path),
                f"origin/{base_branch}",
            )

            logger.info(f"Created worktree: {worktree_path} on branch {branch_name}")

            # Run setup command if provided
            if setup_command:
                await self._run_setup(worktree_path, setup_command)

            return worktree_path

        except WorktreeError:
            # Clean up partial worktree on failure
            if worktree_path.exists():
                await self.remove(issue_identifier)
            raise

    async def _run_setup(self, worktree_path: Path, command: str) -> None:
        """Run a setup command in the worktree.

        Args:
            worktree_path: Path to the worktree
            command: Shell command to run
        """
        logger.info(f"Running setup command in {worktree_path}: {command}")

        process = await asyncio.create_subprocess_shell(
            command,
            cwd=worktree_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            logger.warning(
                f"Setup command failed (non-fatal): {stderr.decode()}"
            )
        else:
            logger.info("Setup command completed successfully")

    async def remove(self, issue_identifier: str, force: bool = False) -> bool:
        """Remove a worktree.

        Args:
            issue_identifier: Issue identifier
            force: Force removal even if there are uncommitted changes

        Returns:
            True if removed successfully
        """
        safe_name = self._sanitize_name(issue_identifier)
        worktree_path = self.worktrees_dir / safe_name
        branch_name = f"claudear/{safe_name}"

        if not worktree_path.exists():
            logger.warning(f"Worktree does not exist: {worktree_path}")
            return False

        logger.info(f"Removing worktree: {worktree_path}")

        try:
            # Remove the worktree
            args = ["worktree", "remove"]
            if force:
                args.append("--force")
            args.append(str(worktree_path))

            await self._run_git(*args)

            # Optionally delete the branch (only if it's been merged or force)
            if force:
                try:
                    await self._run_git("branch", "-D", branch_name)
                    logger.info(f"Deleted branch: {branch_name}")
                except WorktreeError:
                    pass  # Branch might not exist or might be the current branch elsewhere

            return True

        except WorktreeError as e:
            logger.error(f"Failed to remove worktree: {e}")
            return False

    async def list_worktrees(self) -> list[Worktree]:
        """List all worktrees.

        Returns:
            List of Worktree objects
        """
        output = await self._run_git("worktree", "list", "--porcelain")

        worktrees = []
        current: dict[str, str] = {}

        for line in output.split("\n"):
            if not line:
                continue

            if line.startswith("worktree "):
                if current:
                    worktrees.append(self._parse_worktree(current))
                current = {"path": line[9:]}
            elif line.startswith("HEAD "):
                current["commit"] = line[5:]
            elif line.startswith("branch "):
                current["branch"] = line[7:]
            elif line == "bare":
                current["bare"] = "true"

        if current:
            worktrees.append(self._parse_worktree(current))

        return worktrees

    def _parse_worktree(self, data: dict[str, str]) -> Worktree:
        """Parse worktree data from porcelain output.

        Args:
            data: Dict with worktree info

        Returns:
            Worktree object
        """
        path = Path(data.get("path", ""))
        branch = data.get("branch", "")

        # Remove refs/heads/ prefix from branch
        if branch.startswith("refs/heads/"):
            branch = branch[11:]

        # Check if this is the main worktree (the repo itself)
        is_main = path == self.repo_path

        return Worktree(
            path=path,
            branch=branch,
            commit=data.get("commit"),
            is_main=is_main,
        )

    async def get_worktree(self, issue_identifier: str) -> Optional[Worktree]:
        """Get a specific worktree by issue identifier.

        Args:
            issue_identifier: Issue identifier

        Returns:
            Worktree if found, None otherwise
        """
        safe_name = self._sanitize_name(issue_identifier)
        worktree_path = self.worktrees_dir / safe_name

        worktrees = await self.list_worktrees()
        for wt in worktrees:
            if wt.path == worktree_path:
                return wt

        return None

    async def get_worktree_path(self, issue_identifier: str) -> Optional[Path]:
        """Get the path for a worktree by issue identifier.

        Args:
            issue_identifier: Issue identifier

        Returns:
            Path if worktree exists, None otherwise
        """
        safe_name = self._sanitize_name(issue_identifier)
        worktree_path = self.worktrees_dir / safe_name

        if worktree_path.exists():
            return worktree_path
        return None

    async def prune(self) -> None:
        """Prune stale worktree entries.

        This removes worktree entries whose directories have been deleted.
        """
        await self._run_git("worktree", "prune")
        logger.info("Pruned stale worktree entries")

    def get_branch_name(self, issue_identifier: str) -> str:
        """Get the branch name for an issue.

        Args:
            issue_identifier: Issue identifier

        Returns:
            Branch name
        """
        safe_name = self._sanitize_name(issue_identifier)
        return f"claudear/{safe_name}"
