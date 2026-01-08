"""Task manager - orchestrates the full task lifecycle."""
from __future__ import annotations


import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

from claudear.claude.activity import ActivityTracker, get_activity_for_tool
from claudear.claude.runner import ClaudeRunner, ClaudeRunnerPool, SessionResult
from claudear.config import Settings
from claudear.git.github import GitHubClient
from claudear.git.worktree import WorktreeManager
from claudear.linear.client import LinearClient
from claudear.linear.labels import LabelManager, MajorStateLabel
from claudear.linear.models import IssueWebhook
from claudear.tasks.state import TaskContext, TaskState, TaskStateMachine
from claudear.tasks.store import TaskRecord, TaskStore

logger = logging.getLogger(__name__)


@dataclass
class ActiveTask:
    """Represents an active task being worked on."""

    context: TaskContext
    runner: Optional[ClaudeRunner] = None


class TaskManager:
    """Orchestrates the full task lifecycle from Linear to GitHub."""

    def __init__(
        self,
        settings: Settings,
        linear_client: LinearClient,
        worktree_manager: WorktreeManager,
        github_client: GitHubClient,
        task_store: TaskStore,
    ):
        """Initialize the task manager.

        Args:
            settings: Application settings
            linear_client: Linear API client
            worktree_manager: Git worktree manager
            github_client: GitHub client
            task_store: Task persistence store
        """
        self.settings = settings
        self.linear = linear_client
        self.worktrees = worktree_manager
        self.github = github_client
        self.store = task_store

        self._active_tasks: dict[str, ActiveTask] = {}
        self._runner_pool = ClaudeRunnerPool(settings.max_concurrent_tasks)
        self._lock = asyncio.Lock()
        self._comment_poll_task: Optional[asyncio.Task] = None

        # Label management
        self._label_manager: Optional[LabelManager] = None
        self._activity_trackers: dict[str, ActivityTracker] = {}

    async def start(self) -> None:
        """Start the task manager."""
        # Initialize store
        await self.store.init()

        # Initialize label manager if enabled
        if self.settings.labels_enabled:
            self._label_manager = LabelManager(
                self.linear,
                self.settings.linear_team_id,
                debounce_seconds=self.settings.labels_debounce_seconds,
            )
            await self._label_manager.initialize()

        # Recover any in-progress tasks
        await self._recover_tasks()

        # Start comment polling for blocked tasks
        self._comment_poll_task = asyncio.create_task(self._poll_comments())

        logger.info("Task manager started")

    async def stop(self) -> None:
        """Stop the task manager."""
        if self._comment_poll_task:
            self._comment_poll_task.cancel()
            try:
                await self._comment_poll_task
            except asyncio.CancelledError:
                pass

        # Cancel any running tasks
        for issue_id in list(self._active_tasks.keys()):
            await self._runner_pool.cancel_runner(issue_id)

        logger.info("Task manager stopped")

    async def handle_issue_update(self, webhook: IssueWebhook, new_state_id: str) -> None:
        """Handle an issue state update from Linear.

        Args:
            webhook: Issue webhook data
            new_state_id: New state ID
        """
        # Get the state name
        state_name = await self.linear.get_state_name(new_state_id)
        if not state_name:
            logger.warning(f"Unknown state ID: {new_state_id}")
            return

        logger.info(f"Issue {webhook.identifier} moved to '{state_name}'")

        # Check if this is a Todo transition (start working)
        if state_name == self.settings.linear_state_todo:
            await self.start_task(webhook)

        # Check if this is a Done transition (finalize)
        elif state_name == self.settings.linear_state_done:
            await self._handle_done(webhook.id)

    async def start_task(self, issue: IssueWebhook) -> None:
        """Start working on a task.

        Args:
            issue: Issue to work on
        """
        # Check if task already exists in a terminal or advanced state
        existing_task = await self.store.get(issue.id)
        if existing_task and existing_task.state in (
            TaskState.COMPLETED,
            TaskState.IN_REVIEW,
            TaskState.DONE,
        ):
            logger.warning(
                f"Task {issue.identifier} already in state {existing_task.state.value}, ignoring"
            )
            return

        async with self._lock:
            if issue.id in self._active_tasks:
                logger.warning(f"Task {issue.identifier} already active")
                return

            # Re-check DB state inside lock to prevent race with _handle_complete
            existing_task = await self.store.get(issue.id)
            if existing_task and existing_task.state in (
                TaskState.COMPLETED,
                TaskState.IN_REVIEW,
                TaskState.DONE,
            ):
                logger.warning(
                    f"Task {issue.identifier} already in state {existing_task.state.value} (detected inside lock), ignoring"
                )
                return

            # Check concurrency limit
            if len(self._active_tasks) >= self.settings.max_concurrent_tasks:
                logger.warning(
                    f"Max concurrent tasks reached, queueing {issue.identifier}"
                )
                await self.linear.post_comment(
                    issue.id,
                    f"🤖 **Claudear**: Task queued - maximum concurrent tasks ({self.settings.max_concurrent_tasks}) reached. "
                    "Will start automatically when a slot opens.",
                )
                return

        logger.info(f"Starting task: {issue.identifier} - {issue.title}")

        try:
            # 1. Update Linear to In Progress
            await self.linear.update_issue_state(
                issue.id,
                self.settings.linear_state_in_progress,
                team_id=issue.team_id,
            )

            # 2. Create worktree
            branch_name = self.worktrees.get_branch_name(issue.identifier)
            worktree_path = await self.worktrees.create(issue.identifier)

            # 3. Create task context
            context = TaskContext(
                issue_id=issue.id,
                issue_identifier=issue.identifier,
                title=issue.title,
                description=issue.description,
                team_id=issue.team_id,
                branch_name=branch_name,
                worktree_path=str(worktree_path),
            )
            context.state_machine.start()

            # 4. Save to store
            await self._save_task(context)

            # 5. Post status comment
            await self.linear.post_comment(
                issue.id,
                f"🤖 **Claudear**: Starting work on this issue.\n\n"
                f"- Branch: `{branch_name}`\n"
                f"- Status: In Progress",
            )

            # 5b. Set WORKING label
            if self._label_manager:
                await self._label_manager.set_major_state(
                    issue.id, MajorStateLabel.WORKING
                )

            # 6. Create runner and start
            # Set up tool use callback for activity tracking (uses stream-json)
            on_tool_use_callback = None
            if (
                self._label_manager
                and self.settings.labels_activity_enabled
            ):
                # Track last activity to avoid redundant updates
                last_activity = {"value": None}

                def make_on_tool_use(issue_id: str):
                    def on_tool_use(tool_name: str) -> None:
                        activity = get_activity_for_tool(tool_name)
                        if activity and activity != last_activity["value"]:
                            last_activity["value"] = activity
                            if self._label_manager:
                                asyncio.create_task(
                                    self._label_manager.set_activity(issue_id, activity)
                                )
                    return on_tool_use

                on_tool_use_callback = make_on_tool_use(issue.id)

            runner = ClaudeRunner(
                working_dir=worktree_path,
                issue_identifier=issue.identifier,
                title=issue.title,
                description=issue.description,
                on_tool_use=on_tool_use_callback,
                on_blocked=lambda reason: asyncio.create_task(
                    self._handle_blocked(issue.id, reason)
                ),
                on_complete=lambda: asyncio.create_task(
                    self._handle_complete(issue.id)
                ),
            )

            active_task = ActiveTask(context=context, runner=runner)

            async with self._lock:
                self._active_tasks[issue.id] = active_task

            # 7. Run Claude (non-blocking)
            asyncio.create_task(self._run_claude_session(issue.id, runner))

        except Exception as e:
            logger.error(f"Failed to start task {issue.identifier}: {e}")
            await self.linear.post_comment(
                issue.id,
                f"🤖 **Claudear**: Failed to start task.\n\nError: {e}",
            )

    async def _run_claude_session(
        self, issue_id: str, runner: ClaudeRunner
    ) -> None:
        """Run a Claude session for a task.

        Args:
            issue_id: Issue ID
            runner: Claude runner
        """
        try:
            result = await runner.run()

            if result.session_id:
                await self.store.update_session_id(issue_id, result.session_id)

            # Check final state
            if result.is_blocked:
                await self._handle_blocked(issue_id, result.blocked_reason)
            elif result.is_complete:
                await self._handle_complete(issue_id)
            elif result.error:
                await self._handle_error(issue_id, result.error)
            else:
                # Session ended without clear outcome
                logger.warning(
                    f"Session for {issue_id} ended without clear state"
                )

        except Exception as e:
            logger.error(f"Claude session failed: {e}")
            await self._handle_error(issue_id, str(e))

    async def _handle_blocked(
        self, issue_id: str, reason: Optional[str]
    ) -> None:
        """Handle a blocked task.

        Args:
            issue_id: Issue ID
            reason: Reason for blocking
        """
        logger.info(f"Task {issue_id} blocked: {reason}")

        async with self._lock:
            active_task = self._active_tasks.get(issue_id)
            if not active_task:
                return

            active_task.context.state_machine.block(reason or "Unknown reason")

        # Update store
        await self.store.update_state(issue_id, TaskState.BLOCKED, reason)

        # Update labels
        if self._label_manager:
            await self._label_manager.set_major_state(
                issue_id, MajorStateLabel.BLOCKED
            )
            await self._label_manager.set_activity(issue_id, None)  # Clear activity

        # Post comment to Linear
        await self.linear.post_comment(
            issue_id,
            f"🤖 **Claudear is blocked**\n\n"
            f"**Reason**: {reason or 'Unknown'}\n\n"
            f"Please respond with guidance to continue.",
        )

    async def _handle_complete(self, issue_id: str) -> None:
        """Handle task completion.

        Args:
            issue_id: Issue ID
        """
        logger.info(f"Task {issue_id} completed")

        async with self._lock:
            active_task = self._active_tasks.get(issue_id)
            if not active_task:
                logger.warning(f"No active task found for {issue_id}, skipping completion")
                return

            # Prevent double-completion
            if active_task.context.state in (TaskState.COMPLETED, TaskState.IN_REVIEW):
                logger.warning(f"Task {issue_id} already completed, skipping")
                return

            context = active_task.context
            context.state_machine.complete()

            # Update store FIRST while still holding lock to prevent race with delayed webhooks
            await self.store.update_state(issue_id, TaskState.COMPLETED)

            # Then remove from active tasks
            del self._active_tasks[issue_id]

        try:
            # 1. Push to GitHub
            worktree_path = Path(context.worktree_path)
            await self.github.push_branch(worktree_path, context.branch_name)

            # 2. Create PR
            commit_messages = await self.github.get_commit_messages(worktree_path)
            pr_body = self.github.format_pr_body(
                issue_identifier=context.issue_identifier,
                summary=f"Implements {context.title}",
                changes=commit_messages[:10],  # Limit to 10 commits
            )
            pr_title = self.github.format_pr_title(
                issue_identifier=context.issue_identifier,
                title=context.title,
            )

            pr = await self.github.create_pr(
                worktree_path=worktree_path,
                title=pr_title,
                body=pr_body,
            )

            context.pr_number = pr.number
            context.pr_url = pr.url

            # 3. Update store with PR info
            await self.store.update_pr_info(issue_id, pr.number, pr.url)

            # 4. Move to In Review in Linear
            await self.linear.update_issue_state(
                issue_id,
                self.settings.linear_state_in_review,
                team_id=context.team_id,
            )

            # 5. Post completion comment
            await self.linear.post_comment(
                issue_id,
                f"🤖 **Claudear**: Task completed!\n\n"
                f"**Pull Request**: [{pr_title}]({pr.url})\n\n"
                f"Ready for review.",
            )

            # 5b. Update labels to COMPLETED + PR_READY
            if self._label_manager:
                await self._label_manager.set_major_state(
                    issue_id, MajorStateLabel.COMPLETED
                )
                await self._label_manager.add_major_state(
                    issue_id, MajorStateLabel.PR_READY
                )
                await self._label_manager.set_activity(issue_id, None)

            # Clean up activity tracker
            self._activity_trackers.pop(issue_id, None)

            # 6. Update state machine
            context.state_machine.submit_for_review()
            await self.store.update_state(issue_id, TaskState.IN_REVIEW)

        except Exception as e:
            logger.error(f"Failed to complete task {issue_id}: {e}")
            await self._handle_error(issue_id, str(e))

    async def _handle_error(self, issue_id: str, error: str) -> None:
        """Handle a task error.

        Args:
            issue_id: Issue ID
            error: Error message
        """
        logger.error(f"Task {issue_id} failed: {error}")

        async with self._lock:
            active_task = self._active_tasks.get(issue_id)
            if active_task:
                active_task.context.state_machine.fail(error)

        await self.store.update_state(issue_id, TaskState.FAILED, error)

        # Clear all labels on failure
        if self._label_manager:
            await self._label_manager.clear_all_labels(issue_id)

        # Clean up activity tracker
        self._activity_trackers.pop(issue_id, None)

        await self.linear.post_comment(
            issue_id,
            f"🤖 **Claudear**: Task failed\n\n**Error**: {error}\n\n"
            f"Please investigate and retry.",
        )

    async def _handle_done(self, issue_id: str) -> None:
        """Handle issue moved to Done - merge PR and clean up.

        Args:
            issue_id: Issue ID
        """
        logger.info(f"Task {issue_id} marked as done")

        # Get task record to find PR info
        task = await self.store.get(issue_id)
        if not task:
            logger.warning(f"No task record found for {issue_id}")
            return

        async with self._lock:
            active_task = self._active_tasks.get(issue_id)
            if active_task:
                active_task.context.state_machine.mark_done()
                del self._active_tasks[issue_id]

        # Clean up worktree BEFORE merging (so branch can be deleted)
        await self.worktrees.remove(task.issue_identifier)

        # Merge the PR if one exists
        if task.pr_number:
            # Set MERGING label
            if self._label_manager:
                await self._label_manager.clear_all_labels(issue_id)
                await self._label_manager.set_major_state(
                    issue_id, MajorStateLabel.MERGING
                )

            try:
                repo_path = Path(self.settings.repo_path)

                await self.github.merge_pr(
                    worktree_path=repo_path,
                    pr_number=task.pr_number,
                    merge_method="squash",
                    delete_branch=True,
                )

                logger.info(f"Merged PR #{task.pr_number} for {task.issue_identifier}")

                # Set MERGED label
                if self._label_manager:
                    await self._label_manager.set_major_state(
                        issue_id, MajorStateLabel.MERGED
                    )

                # Post completion comment
                await self.linear.post_comment(
                    issue_id,
                    f"🤖 **Claudear**: PR #{task.pr_number} has been merged! 🎉\n\n"
                    f"Branch `{task.branch_name}` has been deleted.",
                )

            except Exception as e:
                logger.error(f"Failed to merge PR for {task.issue_identifier}: {e}")
                # Clear merging label on failure
                if self._label_manager:
                    await self._label_manager.clear_all_labels(issue_id)
                await self.linear.post_comment(
                    issue_id,
                    f"🤖 **Claudear**: Failed to merge PR #{task.pr_number}.\n\n"
                    f"**Error**: {e}\n\n"
                    f"Please merge manually: {task.pr_url}",
                )
        else:
            # No PR, just clear labels
            if self._label_manager:
                await self._label_manager.clear_all_labels(issue_id)

        await self.store.update_state(issue_id, TaskState.DONE)

    async def handle_comment(
        self, issue_id: str, comment_body: str, user_id: str
    ) -> None:
        """Handle a new comment on an issue.

        Args:
            issue_id: Issue ID
            comment_body: Comment text
            user_id: ID of comment author
        """
        # Check if this is a blocked task
        async with self._lock:
            active_task = self._active_tasks.get(issue_id)
            if (
                not active_task
                or active_task.context.state != TaskState.BLOCKED
            ):
                return

        # Check comment is from human (not our bot)
        bot_id = await self.linear.get_bot_user_id()
        if user_id == bot_id:
            return

        logger.info(f"Received human comment on blocked task {issue_id}")

        # Unblock and resume
        active_task.context.state_machine.unblock()
        await self.store.update_state(issue_id, TaskState.IN_PROGRESS)

        # Update label back to WORKING
        if self._label_manager:
            await self._label_manager.set_major_state(
                issue_id, MajorStateLabel.WORKING
            )

        # Resume Claude session
        if active_task.runner:
            result = await active_task.runner.resume(comment_body)

            if result.is_blocked:
                await self._handle_blocked(issue_id, result.blocked_reason)
            elif result.is_complete:
                await self._handle_complete(issue_id)

    async def _poll_comments(self) -> None:
        """Background task to poll for new comments on blocked tasks."""
        while True:
            try:
                await asyncio.sleep(self.settings.comment_poll_interval)

                # Get blocked tasks
                blocked_tasks = await self.store.get_blocked_tasks()

                for task in blocked_tasks:
                    if not task.blocked_at:
                        continue

                    # Check for timeout
                    blocked_duration = (
                        datetime.now() - task.blocked_at
                    ).total_seconds()
                    if blocked_duration > self.settings.blocked_timeout:
                        logger.warning(
                            f"Task {task.issue_identifier} blocked timeout"
                        )
                        await self._handle_error(
                            task.issue_id,
                            f"Blocked for {blocked_duration/3600:.1f} hours without response",
                        )
                        continue

                    # Check for new comments
                    comments = await self.linear.get_new_human_comments(
                        task.issue_id, task.blocked_at
                    )

                    if comments:
                        latest = max(comments, key=lambda c: c.created_at)
                        await self.handle_comment(
                            task.issue_id,
                            latest.body,
                            latest.user.id if latest.user else "",
                        )

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Comment polling error: {e}")

    async def _recover_tasks(self) -> None:
        """Recover tasks that were in progress when we stopped."""
        active_tasks = await self.store.get_active_tasks()

        for task in active_tasks:
            if task.state == TaskState.IN_PROGRESS:
                # Mark as failed - can't resume mid-session
                logger.warning(
                    f"Task {task.issue_identifier} was in progress, marking as failed"
                )
                await self.store.update_state(
                    task.issue_id,
                    TaskState.FAILED,
                    "System restart - please retry",
                )
                await self.linear.post_comment(
                    task.issue_id,
                    "🤖 **Claudear**: System restarted while task was in progress. "
                    "Please move back to 'Todo' to retry.",
                )

            elif task.state == TaskState.BLOCKED:
                # Keep as blocked, will poll for comments
                logger.info(
                    f"Task {task.issue_identifier} still blocked, will poll for response"
                )

    async def _save_task(self, context: TaskContext) -> None:
        """Save task context to store.

        Args:
            context: Task context to save
        """
        record = TaskRecord(
            issue_id=context.issue_id,
            issue_identifier=context.issue_identifier,
            title=context.title,
            description=context.description,
            team_id=context.team_id,
            branch_name=context.branch_name or "",
            worktree_path=context.worktree_path or "",
            state=context.state,
            blocked_reason=context.state_machine.blocked_reason,
            blocked_at=context.state_machine.blocked_at,
            pr_number=context.pr_number,
            pr_url=context.pr_url,
            session_id=context.session_id,
            created_at=context.created_at,
            updated_at=datetime.now(),
        )
        await self.store.save(record)

    def get_active_tasks(self) -> list[TaskContext]:
        """Get all active tasks.

        Returns:
            List of task contexts
        """
        return [task.context for task in self._active_tasks.values()]
