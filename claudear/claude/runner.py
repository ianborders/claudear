"""Claude Code runner using CLI in headless mode with streaming JSON output."""
from __future__ import annotations


import asyncio
import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import AsyncIterator, Callable, Optional

from claudear.claude.hooks import (
    BlockedDetection,
    CompletionDetection,
    build_prompt,
    build_resume_prompt,
    detect_blocked,
    detect_completion,
)

logger = logging.getLogger(__name__)


class ClaudeRunnerError(Exception):
    """Error during Claude execution."""

    pass


@dataclass
class SessionResult:
    """Result of a Claude session."""

    session_id: str
    output: str
    is_blocked: bool = False
    blocked_reason: Optional[str] = None
    is_complete: bool = False
    error: Optional[str] = None
    exit_code: int = 0


@dataclass
class ClaudeSession:
    """Represents a Claude Code session."""

    session_id: str
    working_dir: Path
    issue_identifier: str
    started_at: datetime = field(default_factory=datetime.now)
    last_output: str = ""
    is_blocked: bool = False
    blocked_reason: Optional[str] = None
    is_complete: bool = False


class ClaudeRunner:
    """Runs Claude Code in headless mode for autonomous task execution."""

    def __init__(
        self,
        working_dir: Path,
        issue_identifier: str,
        title: str,
        description: Optional[str] = None,
        on_output: Optional[Callable[[str], None]] = None,
        on_blocked: Optional[Callable[[str], None]] = None,
        on_complete: Optional[Callable[[], None]] = None,
        on_tool_use: Optional[Callable[[str], None]] = None,
    ):
        """Initialize the Claude runner.

        Args:
            working_dir: Directory where Claude will work (worktree path)
            issue_identifier: Issue identifier (e.g., "ENG-123")
            title: Issue title
            description: Issue description
            on_output: Callback for output (streaming)
            on_blocked: Callback when blocked (receives reason)
            on_complete: Callback when task completes
            on_tool_use: Callback when tool is used (receives tool name)
        """
        self.working_dir = Path(working_dir)
        self.issue_identifier = issue_identifier
        self.title = title
        self.description = description
        self.on_output = on_output
        self.on_blocked = on_blocked
        self.on_complete = on_complete
        self.on_tool_use = on_tool_use

        self._session: Optional[ClaudeSession] = None
        self._process: Optional[asyncio.subprocess.Process] = None
        self._output_buffer: list[str] = []

    @property
    def session(self) -> Optional[ClaudeSession]:
        """Get current session."""
        return self._session

    async def run(self, additional_context: Optional[str] = None) -> SessionResult:
        """Run Claude Code on the task.

        Args:
            additional_context: Additional context to include in prompt

        Returns:
            SessionResult with outcome
        """
        session_id = f"claudear-{uuid.uuid4().hex[:8]}"

        self._session = ClaudeSession(
            session_id=session_id,
            working_dir=self.working_dir,
            issue_identifier=self.issue_identifier,
        )

        logger.info(
            f"Starting Claude session {session_id} for {self.issue_identifier}"
        )

        # Build the prompt
        prompt = build_prompt(
            issue_identifier=self.issue_identifier,
            title=self.title,
            description=self.description,
            additional_context=additional_context,
        )

        try:
            result = await self._execute_claude(prompt, session_id)
            return result
        except Exception as e:
            logger.error(f"Claude execution failed: {e}")
            return SessionResult(
                session_id=session_id,
                output="\n".join(self._output_buffer),
                error=str(e),
                exit_code=1,
            )

    async def resume(self, user_input: str) -> SessionResult:
        """Resume a blocked session with user input.

        Args:
            user_input: User's clarification or guidance

        Returns:
            SessionResult with outcome
        """
        if not self._session:
            raise ClaudeRunnerError("No session to resume")

        session_id = self._session.session_id
        logger.info(f"Resuming session {session_id} with user input")

        # Clear blocked state
        self._session.is_blocked = False
        self._session.blocked_reason = None

        # Build resume prompt
        prompt = build_resume_prompt(user_input)

        try:
            result = await self._execute_claude(
                prompt, session_id, resume=True
            )
            return result
        except Exception as e:
            logger.error(f"Resume failed: {e}")
            return SessionResult(
                session_id=session_id,
                output="\n".join(self._output_buffer),
                error=str(e),
                exit_code=1,
            )

    async def _execute_claude(
        self, prompt: str, session_id: str, resume: bool = False
    ) -> SessionResult:
        """Execute Claude CLI with the given prompt.

        Args:
            prompt: Prompt to send
            session_id: Session ID for tracking
            resume: Whether this is a resume operation

        Returns:
            SessionResult
        """
        # Build command - use stream-json for real-time tool event streaming
        cmd = [
            "claude",
            "--print",  # Non-interactive mode
            "--verbose",  # Required for stream-json with --print
            "--output-format",
            "stream-json",  # JSONL streaming for real-time tool events
            "--dangerously-skip-permissions",  # Auto-accept permissions
        ]

        if resume and self._session:
            cmd.extend(["--resume", self._session.session_id])

        logger.debug(f"Executing: {' '.join(cmd)}")
        logger.debug(f"Working dir: {self.working_dir}")

        # Start process
        self._process = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=self.working_dir,
        )

        # Send prompt
        self._process.stdin.write(prompt.encode())
        await self._process.stdin.drain()
        self._process.stdin.close()

        # Collect output
        output_lines = []
        text_content = []  # Extracted text for blocked/complete detection
        stderr_lines = []

        # Read stdout - stream-json outputs JSONL (one JSON object per line)
        async for line in self._read_stream(self._process.stdout):
            output_lines.append(line)
            self._output_buffer.append(line)

            if self.on_output:
                self.on_output(line)

            # Parse JSON line to extract tool events and text
            extracted_text = self._parse_json_line(line)
            if extracted_text:
                text_content.append(extracted_text)

                # Check for blocked state
                blocked = detect_blocked(extracted_text)
                if blocked.is_blocked:
                    self._session.is_blocked = True
                    self._session.blocked_reason = blocked.reason
                    if self.on_blocked:
                        self.on_blocked(blocked.reason or "Unknown reason")

                # Check for completion
                completion = detect_completion(extracted_text)
                if completion.is_complete:
                    self._session.is_complete = True
                    if self.on_complete:
                        self.on_complete()

        # Read stderr
        if self._process.stderr:
            stderr_data = await self._process.stderr.read()
            if stderr_data:
                stderr_lines = stderr_data.decode().split("\n")

        # Wait for process to finish
        await self._process.wait()

        full_output = "\n".join(output_lines)
        full_text = "\n".join(text_content)
        self._session.last_output = full_output

        # Final check for blocked/complete if not detected during streaming
        if not self._session.is_blocked:
            blocked = detect_blocked(full_text)
            if blocked.is_blocked:
                self._session.is_blocked = True
                self._session.blocked_reason = blocked.reason
                if self.on_blocked:
                    self.on_blocked(blocked.reason or "Unknown reason")

        if not self._session.is_complete:
            completion = detect_completion(full_text)
            if completion.is_complete:
                self._session.is_complete = True
                if self.on_complete:
                    self.on_complete()

        return SessionResult(
            session_id=session_id,
            output=full_output,
            is_blocked=self._session.is_blocked,
            blocked_reason=self._session.blocked_reason,
            is_complete=self._session.is_complete,
            exit_code=self._process.returncode or 0,
        )

    async def _read_stream(
        self, stream: asyncio.StreamReader
    ) -> AsyncIterator[str]:
        """Read lines from a stream.

        Args:
            stream: Stream to read from

        Yields:
            Lines from the stream
        """
        while True:
            line = await stream.readline()
            if not line:
                break
            yield line.decode().rstrip()

    def _parse_json_line(self, line: str) -> Optional[str]:
        """Parse a JSON line from stream-json output.

        Extracts tool_use events and calls on_tool_use callback.
        Returns extracted text content for blocked/completion detection.

        Args:
            line: JSON line from Claude output

        Returns:
            Extracted text content, or None if no text
        """
        if not line.strip():
            return None

        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            # Not valid JSON, treat as raw text
            logger.debug(f"Non-JSON line: {line[:80]}")
            return line

        # Extract text content and tool events from message
        text_parts = []
        message = data.get("message", {})
        content = message.get("content", [])

        if isinstance(content, list):
            for item in content:
                if isinstance(item, dict):
                    item_type = item.get("type")

                    if item_type == "text":
                        # Text content
                        text = item.get("text", "")
                        if text:
                            text_parts.append(text)

                    elif item_type == "tool_use":
                        # Tool use event - extract name and call callback
                        tool_name = item.get("name")
                        if tool_name and self.on_tool_use:
                            self.on_tool_use(tool_name)

        # Also check for result content (tool results)
        result = data.get("result")
        if result:
            text_parts.append(str(result))

        return " ".join(text_parts) if text_parts else None

    async def cancel(self) -> None:
        """Cancel the running session."""
        if self._process and self._process.returncode is None:
            logger.info("Cancelling Claude session")
            self._process.terminate()
            try:
                await asyncio.wait_for(self._process.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                self._process.kill()


class ClaudeRunnerPool:
    """Pool for managing multiple Claude runners."""

    def __init__(self, max_concurrent: int = 5):
        """Initialize the runner pool.

        Args:
            max_concurrent: Maximum concurrent runners
        """
        self.max_concurrent = max_concurrent
        self._runners: dict[str, ClaudeRunner] = {}
        self._semaphore = asyncio.Semaphore(max_concurrent)

    async def start_runner(
        self,
        issue_id: str,
        working_dir: Path,
        issue_identifier: str,
        title: str,
        description: Optional[str] = None,
        on_blocked: Optional[Callable[[str], None]] = None,
        on_complete: Optional[Callable[[], None]] = None,
        on_tool_use: Optional[Callable[[str], None]] = None,
    ) -> SessionResult:
        """Start a new runner.

        Args:
            issue_id: Linear issue ID
            working_dir: Working directory
            issue_identifier: Issue identifier
            title: Issue title
            description: Issue description
            on_blocked: Blocked callback
            on_complete: Complete callback
            on_tool_use: Tool use callback (receives tool name)

        Returns:
            SessionResult
        """
        async with self._semaphore:
            runner = ClaudeRunner(
                working_dir=working_dir,
                issue_identifier=issue_identifier,
                title=title,
                description=description,
                on_blocked=on_blocked,
                on_complete=on_complete,
                on_tool_use=on_tool_use,
            )

            self._runners[issue_id] = runner

            try:
                result = await runner.run()
                return result
            finally:
                # Keep runner for potential resume
                pass

    async def resume_runner(
        self, issue_id: str, user_input: str
    ) -> Optional[SessionResult]:
        """Resume a blocked runner.

        Args:
            issue_id: Issue ID of the runner
            user_input: User's input

        Returns:
            SessionResult or None if runner not found
        """
        runner = self._runners.get(issue_id)
        if not runner:
            logger.warning(f"No runner found for issue {issue_id}")
            return None

        async with self._semaphore:
            return await runner.resume(user_input)

    def get_runner(self, issue_id: str) -> Optional[ClaudeRunner]:
        """Get a runner by issue ID.

        Args:
            issue_id: Issue ID

        Returns:
            ClaudeRunner or None
        """
        return self._runners.get(issue_id)

    async def cancel_runner(self, issue_id: str) -> bool:
        """Cancel a running session.

        Args:
            issue_id: Issue ID

        Returns:
            True if cancelled
        """
        runner = self._runners.get(issue_id)
        if runner:
            await runner.cancel()
            del self._runners[issue_id]
            return True
        return False

    @property
    def active_count(self) -> int:
        """Get number of active runners."""
        return len(self._runners)
