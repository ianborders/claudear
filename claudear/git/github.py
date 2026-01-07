"""GitHub integration via gh CLI for PR creation."""
from __future__ import annotations


import asyncio
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class GitHubError(Exception):
    """Error during GitHub operations."""

    pass


@dataclass
class PullRequest:
    """Represents a GitHub pull request."""

    number: int
    url: str
    title: str
    branch: str
    base: str
    state: str = "open"


class GitHubClient:
    """Client for GitHub operations via gh CLI."""

    def __init__(self, token: Optional[str] = None):
        """Initialize the GitHub client.

        Args:
            token: GitHub token (optional, gh CLI may use its own auth)
        """
        self.token = token

    async def _run_gh(
        self, *args: str, cwd: Optional[Path] = None, check: bool = True
    ) -> str:
        """Run a gh CLI command.

        Args:
            *args: Command arguments
            cwd: Working directory
            check: Raise exception on non-zero exit

        Returns:
            Command stdout

        Raises:
            GitHubError: If command fails and check=True
        """
        env = os.environ.copy()
        if self.token:
            env["GH_TOKEN"] = self.token

        process = await asyncio.create_subprocess_exec(
            "gh",
            *args,
            cwd=cwd,
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()

        if check and process.returncode != 0:
            error_msg = stderr.decode().strip() or stdout.decode().strip()
            raise GitHubError(f"gh command failed: gh {' '.join(args)}\n{error_msg}")

        return stdout.decode().strip()

    async def _run_git(
        self, *args: str, cwd: Optional[Path] = None, check: bool = True
    ) -> str:
        """Run a git command.

        Args:
            *args: Command arguments
            cwd: Working directory
            check: Raise exception on non-zero exit

        Returns:
            Command stdout
        """
        process = await asyncio.create_subprocess_exec(
            "git",
            *args,
            cwd=cwd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()

        if check and process.returncode != 0:
            error_msg = stderr.decode().strip() or stdout.decode().strip()
            raise GitHubError(f"git command failed: git {' '.join(args)}\n{error_msg}")

        return stdout.decode().strip()

    async def push_branch(
        self,
        worktree_path: Path,
        branch_name: str,
        force: bool = False,
    ) -> bool:
        """Push a branch to the remote.

        Args:
            worktree_path: Path to the worktree
            branch_name: Branch name to push
            force: Force push (use with caution)

        Returns:
            True if push was successful
        """
        logger.info(f"Pushing branch {branch_name} from {worktree_path}")

        args = ["push", "-u", "origin", branch_name]
        if force:
            args.insert(1, "--force")

        try:
            await self._run_git(*args, cwd=worktree_path)
            logger.info(f"Successfully pushed branch {branch_name}")
            return True
        except GitHubError as e:
            logger.error(f"Failed to push branch: {e}")
            raise

    async def create_pr(
        self,
        worktree_path: Path,
        title: str,
        body: str,
        base_branch: str = "main",
        draft: bool = False,
    ) -> PullRequest:
        """Create a pull request.

        Args:
            worktree_path: Path to the worktree
            title: PR title
            body: PR body (markdown)
            base_branch: Base branch to merge into
            draft: Create as draft PR

        Returns:
            PullRequest object
        """
        logger.info(f"Creating PR: {title}")

        args = [
            "pr",
            "create",
            "--title",
            title,
            "--body",
            body,
            "--base",
            base_branch,
        ]

        if draft:
            args.append("--draft")

        try:
            # Create PR and get URL
            output = await self._run_gh(*args, cwd=worktree_path)
            pr_url = output.strip()

            # Extract PR number from URL
            # URL format: https://github.com/owner/repo/pull/123
            pr_number = int(pr_url.split("/")[-1])

            # Get current branch name
            branch = await self._run_git("branch", "--show-current", cwd=worktree_path)

            logger.info(f"Created PR #{pr_number}: {pr_url}")

            return PullRequest(
                number=pr_number,
                url=pr_url,
                title=title,
                branch=branch,
                base=base_branch,
            )

        except GitHubError as e:
            logger.error(f"Failed to create PR: {e}")
            raise

    async def get_pr_for_branch(
        self, worktree_path: Path, branch_name: str
    ) -> Optional[PullRequest]:
        """Get existing PR for a branch.

        Args:
            worktree_path: Path to the worktree
            branch_name: Branch name

        Returns:
            PullRequest if exists, None otherwise
        """
        try:
            output = await self._run_gh(
                "pr",
                "view",
                branch_name,
                "--json",
                "number,url,title,headRefName,baseRefName,state",
                cwd=worktree_path,
                check=False,
            )

            if not output:
                return None

            import json

            data = json.loads(output)

            return PullRequest(
                number=data["number"],
                url=data["url"],
                title=data["title"],
                branch=data["headRefName"],
                base=data["baseRefName"],
                state=data["state"],
            )

        except (GitHubError, json.JSONDecodeError):
            return None

    async def add_pr_comment(
        self, worktree_path: Path, pr_number: int, body: str
    ) -> bool:
        """Add a comment to a pull request.

        Args:
            worktree_path: Path to the worktree
            pr_number: PR number
            body: Comment body

        Returns:
            True if comment was added
        """
        try:
            await self._run_gh(
                "pr",
                "comment",
                str(pr_number),
                "--body",
                body,
                cwd=worktree_path,
            )
            logger.info(f"Added comment to PR #{pr_number}")
            return True
        except GitHubError as e:
            logger.error(f"Failed to add PR comment: {e}")
            return False

    def format_pr_body(
        self,
        issue_identifier: str,
        summary: str,
        changes: Optional[list[str]] = None,
    ) -> str:
        """Format a PR body with Linear issue link.

        Args:
            issue_identifier: Linear issue identifier (e.g., "ENG-123")
            summary: Summary of changes
            changes: List of change descriptions

        Returns:
            Formatted PR body
        """
        body_parts = [
            "## Summary",
            summary,
            "",
            "## Linear Issue",
            f"Closes {issue_identifier}",
            "",
        ]

        if changes:
            body_parts.extend(["## Changes", ""])
            for change in changes:
                body_parts.append(f"- {change}")
            body_parts.append("")

        body_parts.extend(
            [
                "---",
                "🤖 Generated by Claudear",
            ]
        )

        return "\n".join(body_parts)

    def format_pr_title(
        self, issue_identifier: str, title: str, pr_type: str = "feat"
    ) -> str:
        """Format a PR title.

        Args:
            issue_identifier: Linear issue identifier
            title: Issue title
            pr_type: Type prefix (feat, fix, chore, etc.)

        Returns:
            Formatted PR title
        """
        # Clean up the title
        clean_title = title.strip()
        if clean_title.endswith("."):
            clean_title = clean_title[:-1]

        return f"{pr_type}({issue_identifier}): {clean_title}"

    async def commit_changes(
        self,
        worktree_path: Path,
        message: str,
        add_all: bool = True,
    ) -> bool:
        """Commit changes in a worktree.

        Args:
            worktree_path: Path to the worktree
            message: Commit message
            add_all: Add all changes before committing

        Returns:
            True if commit was made
        """
        try:
            if add_all:
                await self._run_git("add", "-A", cwd=worktree_path)

            # Check if there are changes to commit
            status = await self._run_git(
                "status", "--porcelain", cwd=worktree_path
            )
            if not status:
                logger.info("No changes to commit")
                return False

            await self._run_git(
                "commit", "-m", message, cwd=worktree_path
            )
            logger.info(f"Committed changes: {message[:50]}...")
            return True

        except GitHubError as e:
            logger.error(f"Failed to commit: {e}")
            raise

    async def merge_pr(
        self,
        worktree_path: Path,
        pr_number: int,
        merge_method: str = "squash",
        delete_branch: bool = True,
    ) -> bool:
        """Merge a pull request.

        Args:
            worktree_path: Path to the worktree
            pr_number: PR number to merge
            merge_method: Merge method (merge, squash, rebase)
            delete_branch: Delete branch after merge

        Returns:
            True if merge was successful
        """
        logger.info(f"Merging PR #{pr_number} using {merge_method}")

        args = [
            "pr",
            "merge",
            str(pr_number),
            f"--{merge_method}",
        ]

        if delete_branch:
            args.append("--delete-branch")

        try:
            await self._run_gh(*args, cwd=worktree_path)
            logger.info(f"Successfully merged PR #{pr_number}")
            return True
        except GitHubError as e:
            logger.error(f"Failed to merge PR: {e}")
            raise

    async def get_commit_messages(
        self, worktree_path: Path, base_branch: str = "main", limit: int = 20
    ) -> list[str]:
        """Get commit messages for the current branch since diverging from base.

        Args:
            worktree_path: Path to the worktree
            base_branch: Base branch
            limit: Maximum number of commits

        Returns:
            List of commit messages
        """
        try:
            output = await self._run_git(
                "log",
                f"origin/{base_branch}..HEAD",
                f"--max-count={limit}",
                "--format=%s",
                cwd=worktree_path,
            )
            return [msg for msg in output.split("\n") if msg]
        except GitHubError:
            return []
