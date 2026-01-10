"""Unified TaskOrchestrator for multi-provider task automation."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional, Any, TYPE_CHECKING

from claudear.core.types import (
    TaskId,
    TaskStatus,
    ProviderType,
    ProviderInstance,
    UnifiedTask,
)
from claudear.core.state import TaskContext, TaskState, TaskStateMachine
from claudear.core.store import TaskStore, TaskRecord
from claudear.events.types import (
    Event,
    EventType,
    TaskStatusChangedEvent,
    TaskCommentAddedEvent,
)
from claudear.providers.base import PMProvider, EventSource
from claudear.git.worktree import WorktreeManager
from claudear.git.github import GitHubClient

if TYPE_CHECKING:
    from claudear.claude.runner import ClaudeRunner, ClaudeRunnerPool

logger = logging.getLogger(__name__)


@dataclass
class ActiveTask:
    """Represents an active task being worked on."""

    context: TaskContext
    task_id: TaskId
    runner: Optional["ClaudeRunner"] = None


@dataclass
class InstanceResources:
    """Resources specific to a provider instance (team/database)."""

    instance: ProviderInstance
    worktree_manager: WorktreeManager
    github_client: GitHubClient


class TaskOrchestrator:
    """Orchestrates tasks across multiple providers and instances.

    This is the unified task manager that replaces provider-specific
    TaskManagers. It handles:
    - Multiple providers (Linear, Notion)
    - Multiple instances per provider (teams, databases)
    - Per-instance git worktrees and GitHub integration
    - Shared Claude runner pool
    - Event routing and task lifecycle
    """

    def __init__(
        self,
        task_store: TaskStore,
        github_token: Optional[str] = None,
        max_concurrent_tasks: int = 3,
        comment_poll_interval: int = 30,
        blocked_timeout: int = 86400,  # 24 hours
    ):
        """Initialize the orchestrator.

        Args:
            task_store: Shared task persistence store
            github_token: GitHub token for PR operations
            max_concurrent_tasks: Maximum concurrent tasks across all instances
            comment_poll_interval: Seconds between comment polls for blocked tasks
            blocked_timeout: Seconds before a blocked task times out
        """
        self.store = task_store
        self._github_token = github_token
        self._max_concurrent_tasks = max_concurrent_tasks
        self._comment_poll_interval = comment_poll_interval
        self._blocked_timeout = blocked_timeout

        # Providers: provider_type -> PMProvider
        self._providers: dict[ProviderType, PMProvider] = {}

        # Instance resources: (provider_type, instance_id) -> InstanceResources
        self._instance_resources: dict[tuple[ProviderType, str], InstanceResources] = {}

        # Active tasks: composite_key -> ActiveTask
        self._active_tasks: dict[str, ActiveTask] = {}

        # Claude runner pool (shared across all instances)
        self._runner_pool: Optional["ClaudeRunnerPool"] = None

        # Locks and background tasks (created lazily)
        self._lock: Optional[asyncio.Lock] = None
        self._comment_poll_task: Optional[asyncio.Task] = None

    def _get_lock(self) -> asyncio.Lock:
        """Get or create the async lock."""
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    def register_provider(self, provider: PMProvider) -> None:
        """Register a provider with the orchestrator.

        Args:
            provider: Provider to register
        """
        self._providers[provider.provider_type] = provider
        logger.info(f"Registered provider: {provider.display_name}")

    async def register_instance(self, instance: ProviderInstance) -> None:
        """Register and initialize a provider instance.

        Sets up per-instance resources (WorktreeManager, GitHubClient).

        Args:
            instance: Instance to register
        """
        provider = self._providers.get(instance.provider)
        if not provider:
            raise ValueError(f"Provider {instance.provider} not registered")

        # Initialize provider-side instance
        await provider.initialize_instance(instance)

        # Set up per-instance resources
        worktree_manager = WorktreeManager(str(instance.repo_path))
        github_client = GitHubClient(self._github_token)

        resources = InstanceResources(
            instance=instance,
            worktree_manager=worktree_manager,
            github_client=github_client,
        )

        key = (instance.provider, instance.instance_id)
        self._instance_resources[key] = resources

        # Set up event source with our handler
        event_source = provider.get_event_source(instance)
        event_source.set_event_handler(self._handle_event)

        logger.info(
            f"Registered instance: {instance.display_name} "
            f"(repo: {instance.repo_path})"
        )

    async def start(self) -> None:
        """Start the orchestrator and all event sources."""
        # Initialize store
        await self.store.init()

        # Initialize Claude runner pool
        from claudear.claude.runner import ClaudeRunnerPool

        self._runner_pool = ClaudeRunnerPool(self._max_concurrent_tasks)

        # Start event sources for all instances
        for key, resources in self._instance_resources.items():
            provider_type, instance_id = key
            provider = self._providers[provider_type]
            event_source = provider.get_event_source(resources.instance)
            await event_source.start()

        # Recover any in-progress tasks
        await self._recover_tasks()

        # Start comment polling for blocked tasks
        self._comment_poll_task = asyncio.create_task(self._poll_comments())

        logger.info("Task orchestrator started")

    async def stop(self) -> None:
        """Stop the orchestrator and all event sources."""
        # Stop comment polling
        if self._comment_poll_task:
            self._comment_poll_task.cancel()
            try:
                await self._comment_poll_task
            except asyncio.CancelledError:
                pass

        # Cancel any running tasks
        for composite_key in list(self._active_tasks.keys()):
            if self._runner_pool:
                await self._runner_pool.cancel_runner(composite_key)

        # Stop event sources
        for key, resources in self._instance_resources.items():
            provider_type, instance_id = key
            provider = self._providers[provider_type]
            event_source = provider.get_event_source(resources.instance)
            await event_source.stop()

        # Shutdown providers
        for provider in self._providers.values():
            await provider.shutdown()

        logger.info("Task orchestrator stopped")

    def _get_resources(self, task_id: TaskId) -> Optional[InstanceResources]:
        """Get resources for a task's instance.

        Args:
            task_id: Task identifier

        Returns:
            Instance resources or None if not found
        """
        key = (task_id.provider, task_id.instance_id)
        return self._instance_resources.get(key)

    def _get_provider(self, task_id: TaskId) -> Optional[PMProvider]:
        """Get the provider for a task.

        Args:
            task_id: Task identifier

        Returns:
            Provider or None if not found
        """
        return self._providers.get(task_id.provider)

    # -------------------------------------------------------------------------
    # Event Handling
    # -------------------------------------------------------------------------

    async def _handle_event(self, event: Event) -> None:
        """Handle an event from any provider.

        Routes events to appropriate handlers based on type.

        Args:
            event: Event to handle
        """
        try:
            if event.type == EventType.TASK_STATUS_CHANGED:
                await self._handle_status_change(event)  # type: ignore
            elif event.type == EventType.TASK_COMMENT_ADDED:
                await self._handle_comment(event)  # type: ignore
            else:
                logger.debug(f"Ignoring event type: {event.type}")
        except Exception as e:
            logger.error(f"Error handling event: {e}")

    async def _handle_status_change(self, event: TaskStatusChangedEvent) -> None:
        """Handle a task status change event.

        Args:
            event: Status change event
        """
        task_id = event.task_id

        logger.info(
            f"Status change: {task_id.identifier} "
            f"{event.old_status.value if event.old_status else 'unknown'} -> "
            f"{event.new_status.value}"
        )

        # Handle based on new status
        if event.new_status == TaskStatus.TODO:
            await self._start_task(task_id, event.task_title, event.task_description)
        elif event.new_status == TaskStatus.DONE:
            await self._handle_done(task_id)

    async def _handle_comment(self, event: TaskCommentAddedEvent) -> None:
        """Handle a new comment event.

        Args:
            event: Comment event
        """
        if event.is_bot_comment:
            return

        task_id = event.task_id
        composite_key = task_id.composite_key

        async with self._get_lock():
            active_task = self._active_tasks.get(composite_key)
            if not active_task or active_task.context.state != TaskState.BLOCKED:
                return

        logger.info(f"Human comment on blocked task {task_id.identifier}")
        await self._handle_unblock(task_id, event.comment_body)

    # -------------------------------------------------------------------------
    # Task Lifecycle
    # -------------------------------------------------------------------------

    async def _start_task(
        self,
        task_id: TaskId,
        title: str,
        description: Optional[str],
    ) -> None:
        """Start working on a task.

        Args:
            task_id: Task identifier
            title: Task title
            description: Task description
        """
        composite_key = task_id.composite_key

        # Check if already active or completed
        existing = await self.store.get(
            task_id.provider, task_id.instance_id, task_id.external_id
        )
        if existing and existing.state in (
            TaskState.COMPLETED,
            TaskState.IN_REVIEW,
            TaskState.DONE,
        ):
            logger.warning(
                f"Task {task_id.identifier} already in state {existing.state.value}"
            )
            return

        async with self._get_lock():
            if composite_key in self._active_tasks:
                logger.warning(f"Task {task_id.identifier} already active")
                return

            # Check concurrency limit
            if len(self._active_tasks) >= self._max_concurrent_tasks:
                logger.warning(f"Max concurrent tasks reached, queueing {task_id.identifier}")
                provider = self._get_provider(task_id)
                if provider:
                    await provider.post_comment(
                        task_id,
                        f"🤖 **Claudear**: Task queued - maximum concurrent tasks "
                        f"({self._max_concurrent_tasks}) reached. "
                        "Will start automatically when a slot opens.",
                    )
                return

        logger.info(f"Starting task: {task_id.identifier} - {title}")

        resources = self._get_resources(task_id)
        provider = self._get_provider(task_id)

        if not resources or not provider:
            logger.error(f"No resources/provider for {task_id.composite_key}")
            return

        try:
            # 1. Update status to In Progress
            await provider.update_task_status(task_id, TaskStatus.IN_PROGRESS)

            # 2. Create worktree
            branch_name = resources.worktree_manager.get_branch_name(task_id.identifier)
            worktree_path = await resources.worktree_manager.create(task_id.identifier)

            # 3. Create task context
            context = TaskContext(
                task_id=task_id,
                title=title,
                description=description,
                branch_name=branch_name,
                worktree_path=str(worktree_path),
            )
            context.state_machine.start()

            # 4. Save to store
            await self._save_task(task_id, context)

            # 5. Post status comment
            await provider.post_comment(
                task_id,
                f"🤖 **Claudear**: Starting work on this issue.\n\n"
                f"- Branch: `{branch_name}`\n"
                f"- Status: In Progress",
            )

            # 6. Set working indicator
            await provider.set_working_indicator(task_id, "🚀 Starting...")

            # 7. Create runner and start
            from claudear.claude.runner import ClaudeRunner
            from claudear.claude.activity import get_activity_for_tool

            # Create tool use callback for real-time status updates
            def on_tool_use_callback(tool_name: str) -> None:
                activity = get_activity_for_tool(tool_name)
                if activity and provider:
                    asyncio.create_task(
                        provider.set_working_indicator(task_id, activity.display_text)
                    )

            runner = ClaudeRunner(
                working_dir=worktree_path,
                issue_identifier=task_id.identifier,
                title=title,
                description=description,
                on_blocked=lambda reason: asyncio.create_task(
                    self._handle_blocked(task_id, reason)
                ),
                on_complete=lambda: asyncio.create_task(
                    self._handle_complete(task_id)
                ),
                on_tool_use=on_tool_use_callback,
            )

            active_task = ActiveTask(
                context=context,
                task_id=task_id,
                runner=runner,
            )

            async with self._get_lock():
                self._active_tasks[composite_key] = active_task

            # 8. Run Claude (non-blocking)
            asyncio.create_task(self._run_claude_session(task_id, runner))

        except Exception as e:
            logger.error(f"Failed to start task {task_id.identifier}: {e}")
            if provider:
                await provider.post_comment(
                    task_id,
                    f"🤖 **Claudear**: Failed to start task.\n\nError: {e}",
                )

    async def _run_claude_session(
        self, task_id: TaskId, runner: "ClaudeRunner"
    ) -> None:
        """Run a Claude session for a task.

        Args:
            task_id: Task identifier
            runner: Claude runner
        """
        try:
            result = await runner.run()

            if result.session_id:
                await self.store.update_session_id(
                    task_id.provider,
                    task_id.instance_id,
                    task_id.external_id,
                    result.session_id,
                )

            if result.is_blocked:
                await self._handle_blocked(task_id, result.blocked_reason)
            elif result.is_complete:
                await self._handle_complete(task_id)
            elif result.error:
                await self._handle_error(task_id, result.error)
            else:
                logger.warning(f"Session for {task_id.identifier} ended without clear state")

        except Exception as e:
            logger.error(f"Claude session failed: {e}")
            await self._handle_error(task_id, str(e))

    async def _handle_blocked(
        self, task_id: TaskId, reason: Optional[str]
    ) -> None:
        """Handle a blocked task.

        Args:
            task_id: Task identifier
            reason: Reason for blocking
        """
        composite_key = task_id.composite_key
        logger.info(f"Task {task_id.identifier} blocked: {reason}")

        async with self._get_lock():
            active_task = self._active_tasks.get(composite_key)
            if not active_task:
                return
            active_task.context.state_machine.block(reason or "Unknown reason")

        # Update store
        await self.store.update_state(
            task_id.provider,
            task_id.instance_id,
            task_id.external_id,
            TaskState.BLOCKED,
            reason,
        )

        # Update provider indicators
        provider = self._get_provider(task_id)
        if provider:
            await provider.set_blocked_indicator(task_id, reason)
            await provider.post_comment(
                task_id,
                f"🤖 **Claudear is blocked**\n\n"
                f"**Reason**: {reason or 'Unknown'}\n\n"
                f"Please respond with guidance to continue.",
            )

    async def _handle_unblock(self, task_id: TaskId, comment_body: str) -> None:
        """Handle unblocking a task via human comment.

        Args:
            task_id: Task identifier
            comment_body: Human response comment
        """
        composite_key = task_id.composite_key

        async with self._get_lock():
            active_task = self._active_tasks.get(composite_key)
            if not active_task:
                return
            active_task.context.state_machine.unblock()

        await self.store.update_state(
            task_id.provider,
            task_id.instance_id,
            task_id.external_id,
            TaskState.IN_PROGRESS,
        )

        provider = self._get_provider(task_id)
        if provider:
            await provider.set_working_indicator(task_id, "🔄 Resuming...")

        # Resume Claude session
        if active_task.runner:
            result = await active_task.runner.resume(comment_body)

            if result.is_blocked:
                await self._handle_blocked(task_id, result.blocked_reason)
            elif result.is_complete:
                await self._handle_complete(task_id)

    async def _handle_complete(self, task_id: TaskId) -> None:
        """Handle task completion.

        Args:
            task_id: Task identifier
        """
        composite_key = task_id.composite_key
        logger.info(f"Task {task_id.identifier} completed")

        async with self._get_lock():
            active_task = self._active_tasks.get(composite_key)
            if not active_task:
                logger.warning(f"No active task found for {task_id.identifier}")
                return

            if active_task.context.state in (TaskState.COMPLETED, TaskState.IN_REVIEW):
                logger.warning(f"Task {task_id.identifier} already completed")
                return

            context = active_task.context
            context.state_machine.complete()

            # Update store first
            await self.store.update_state(
                task_id.provider,
                task_id.instance_id,
                task_id.external_id,
                TaskState.COMPLETED,
            )

            del self._active_tasks[composite_key]

        resources = self._get_resources(task_id)
        provider = self._get_provider(task_id)

        if not resources or not provider:
            return

        try:
            # 1. Show pushing status
            await provider.set_working_indicator(task_id, "📤 Pushing to GitHub...")

            # 2. Push to GitHub
            worktree_path = Path(context.worktree_path)
            await resources.github_client.push_branch(
                worktree_path, context.branch_name
            )

            # 3. Show PR creation status
            await provider.set_working_indicator(task_id, "📝 Creating PR...")

            # 4. Create PR
            commit_messages = await resources.github_client.get_commit_messages(
                worktree_path
            )
            pr_body = resources.github_client.format_pr_body(
                issue_identifier=task_id.identifier,
                summary=f"Implements {context.title}",
                changes=commit_messages[:10],
            )
            pr_title = resources.github_client.format_pr_title(
                issue_identifier=task_id.identifier,
                title=context.title,
            )

            pr = await resources.github_client.create_pr(
                worktree_path=worktree_path,
                title=pr_title,
                body=pr_body,
            )

            context.pr_number = pr.number
            context.pr_url = pr.url

            # 3. Update store with PR info
            await self.store.update_pr_info(
                task_id.provider,
                task_id.instance_id,
                task_id.external_id,
                pr.number,
                pr.url,
            )

            # 4. Update provider status
            await provider.update_task_status(task_id, TaskStatus.IN_REVIEW)
            await provider.set_branch_info(task_id, context.branch_name, pr.url)

            # 5. Post completion comment
            await provider.post_comment(
                task_id,
                f"🤖 **Claudear**: Task completed!\n\n"
                f"**Pull Request**: [{pr_title}]({pr.url})\n\n"
                f"Ready for review.",
            )

            # 6. Show PR ready status
            await provider.set_working_indicator(task_id, "✅ PR ready for review")

            # 7. Update state to IN_REVIEW
            context.state_machine.submit_for_review()
            await self.store.update_state(
                task_id.provider,
                task_id.instance_id,
                task_id.external_id,
                TaskState.IN_REVIEW,
            )

        except Exception as e:
            logger.error(f"Failed to complete task {task_id.identifier}: {e}")
            await self._handle_error(task_id, str(e))

    async def _handle_done(self, task_id: TaskId) -> None:
        """Handle task marked as done - merge PR and clean up.

        Args:
            task_id: Task identifier
        """
        logger.info(f"Task {task_id.identifier} marked as done")

        # Get task record
        task = await self.store.get(
            task_id.provider, task_id.instance_id, task_id.external_id
        )
        if not task:
            logger.warning(f"No task record found for {task_id.identifier}")
            return

        composite_key = task_id.composite_key

        async with self._get_lock():
            if composite_key in self._active_tasks:
                active_task = self._active_tasks[composite_key]
                active_task.context.state_machine.mark_done()
                del self._active_tasks[composite_key]

        resources = self._get_resources(task_id)
        provider = self._get_provider(task_id)

        if not resources:
            return

        # Clean up worktree
        await resources.worktree_manager.remove(task.task_identifier)

        # Merge PR if exists
        if task.pr_number:
            try:
                # Show merging status
                if provider:
                    await provider.set_working_indicator(task_id, "🔀 Merging PR...")

                await resources.github_client.merge_pr(
                    worktree_path=resources.instance.repo_path,
                    pr_number=task.pr_number,
                    merge_method="squash",
                    delete_branch=True,
                )

                logger.info(f"Merged PR #{task.pr_number} for {task.task_identifier}")

                if provider:
                    await provider.post_comment(
                        task_id,
                        f"🤖 **Claudear**: PR #{task.pr_number} has been merged! 🎉\n\n"
                        f"Branch `{task.branch_name}` has been deleted.",
                    )
                    # Show merged status instead of clearing
                    await provider.set_working_indicator(task_id, "✅ Merged")

            except Exception as e:
                logger.error(f"Failed to merge PR: {e}")
                if provider:
                    await provider.set_working_indicator(task_id, "❌ Merge failed")
                    await provider.post_comment(
                        task_id,
                        f"🤖 **Claudear**: Failed to merge PR #{task.pr_number}.\n\n"
                        f"**Error**: {e}\n\n"
                        f"Please merge manually: {task.pr_url}",
                    )

        await self.store.update_state(
            task_id.provider,
            task_id.instance_id,
            task_id.external_id,
            TaskState.DONE,
        )

    async def _handle_error(self, task_id: TaskId, error: str) -> None:
        """Handle a task error.

        Args:
            task_id: Task identifier
            error: Error message
        """
        composite_key = task_id.composite_key
        logger.error(f"Task {task_id.identifier} failed: {error}")

        async with self._get_lock():
            active_task = self._active_tasks.get(composite_key)
            if active_task:
                active_task.context.state_machine.fail(error)
                del self._active_tasks[composite_key]

        await self.store.update_state(
            task_id.provider,
            task_id.instance_id,
            task_id.external_id,
            TaskState.FAILED,
            error,
        )

        provider = self._get_provider(task_id)
        if provider:
            await provider.clear_indicators(task_id)
            await provider.post_comment(
                task_id,
                f"🤖 **Claudear**: Task failed\n\n**Error**: {error}\n\n"
                f"Please investigate and retry.",
            )

    # -------------------------------------------------------------------------
    # Background Tasks
    # -------------------------------------------------------------------------

    async def _poll_comments(self) -> None:
        """Background task to poll for new comments on blocked tasks."""
        while True:
            try:
                await asyncio.sleep(self._comment_poll_interval)

                blocked_tasks = await self.store.get_blocked_tasks()

                for task in blocked_tasks:
                    if not task.blocked_at:
                        continue

                    # Check for timeout
                    blocked_duration = (
                        datetime.now() - task.blocked_at
                    ).total_seconds()
                    if blocked_duration > self._blocked_timeout:
                        task_id = TaskId(
                            provider=task.provider,
                            instance_id=task.instance_id,
                            external_id=task.external_id,
                            identifier=task.task_identifier,
                        )
                        await self._handle_error(
                            task_id,
                            f"Blocked for {blocked_duration/3600:.1f} hours without response",
                        )
                        continue

                    # Check for new comments via provider
                    task_id = TaskId(
                        provider=task.provider,
                        instance_id=task.instance_id,
                        external_id=task.external_id,
                        identifier=task.task_identifier,
                    )
                    provider = self._get_provider(task_id)
                    if provider:
                        comments = await provider.get_new_comments(
                            task_id, task.blocked_at
                        )
                        if comments:
                            latest = max(comments, key=lambda c: c["created_at"])
                            await self._handle_unblock(task_id, latest["body"])

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Comment polling error: {e}")

    async def _recover_tasks(self) -> None:
        """Recover tasks that were in progress when we stopped."""
        active_tasks = await self.store.get_active_tasks()

        for task in active_tasks:
            task_id = TaskId(
                provider=task.provider,
                instance_id=task.instance_id,
                external_id=task.external_id,
                identifier=task.task_identifier,
            )
            provider = self._get_provider(task_id)

            if task.state == TaskState.IN_PROGRESS:
                logger.warning(
                    f"Task {task.task_identifier} was in progress, marking as failed"
                )
                await self.store.update_state(
                    task.provider,
                    task.instance_id,
                    task.external_id,
                    TaskState.FAILED,
                    "System restart - please retry",
                )
                if provider:
                    await provider.post_comment(
                        task_id,
                        "🤖 **Claudear**: System restarted while task was in progress. "
                        "Please move back to 'Todo' to retry.",
                    )

            elif task.state == TaskState.BLOCKED:
                logger.info(
                    f"Task {task.task_identifier} still blocked, will poll for response"
                )

    # -------------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------------

    async def _save_task(self, task_id: TaskId, context: TaskContext) -> None:
        """Save task context to store.

        Args:
            task_id: Task identifier
            context: Task context to save
        """
        record = TaskRecord(
            provider=task_id.provider,
            instance_id=task_id.instance_id,
            external_id=task_id.external_id,
            task_identifier=task_id.identifier,
            title=context.title,
            description=context.description,
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

    def get_active_tasks(self) -> list[ActiveTask]:
        """Get all active tasks.

        Returns:
            List of active tasks
        """
        return list(self._active_tasks.values())

    def get_instance_info(self) -> list[dict[str, Any]]:
        """Get information about registered instances.

        Returns:
            List of instance info dicts
        """
        return [
            {
                "provider": key[0].value,
                "instance_id": key[1],
                "display_name": resources.instance.display_name,
                "repo_path": str(resources.instance.repo_path),
            }
            for key, resources in self._instance_resources.items()
        ]
