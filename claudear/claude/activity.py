"""Claude output parser for activity detection."""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Optional

from claudear.linear.labels import ActivityLabel

logger = logging.getLogger(__name__)


# Mapping of Claude Code tool names to activity labels
TOOL_NAME_TO_ACTIVITY: dict[str, ActivityLabel] = {
    # Reading tools
    "Read": ActivityLabel.READING,
    "Glob": ActivityLabel.SEARCHING,
    "Grep": ActivityLabel.SEARCHING,
    # Writing/editing tools
    "Edit": ActivityLabel.EDITING,
    "Write": ActivityLabel.EDITING,
    "NotebookEdit": ActivityLabel.EDITING,
    # Bash - categorize based on common patterns (default to TESTING for builds/tests)
    "Bash": ActivityLabel.TESTING,  # Default - often used for tests/builds
    # Search tools
    "WebSearch": ActivityLabel.SEARCHING,
    "WebFetch": ActivityLabel.SEARCHING,
    # Task/agent tools
    "Task": ActivityLabel.THINKING,
    # Todo tracking
    "TodoWrite": ActivityLabel.THINKING,
}


def get_activity_for_tool(tool_name: str) -> Optional[ActivityLabel]:
    """Get activity label for a Claude Code tool name.

    Args:
        tool_name: Name of the tool (e.g., "Read", "Edit", "Bash")

    Returns:
        ActivityLabel or None if tool not mapped
    """
    return TOOL_NAME_TO_ACTIVITY.get(tool_name)


@dataclass
class ActivityDetection:
    """Result of activity detection."""

    activity: Optional[ActivityLabel]
    tool_name: Optional[str] = None


# Claude Code tool patterns (based on --print output format)
# These patterns match tool invocations in Claude's output
TOOL_PATTERNS: list[tuple[re.Pattern, ActivityLabel, str]] = [
    # Reading patterns
    (re.compile(r"\bRead\b", re.IGNORECASE), ActivityLabel.READING, "Read"),
    (re.compile(r"Reading\s+file", re.IGNORECASE), ActivityLabel.READING, "Read"),
    (re.compile(r"\bcat\s+", re.IGNORECASE), ActivityLabel.READING, "cat"),
    (re.compile(r"\bhead\s+", re.IGNORECASE), ActivityLabel.READING, "head"),
    (re.compile(r"\btail\s+", re.IGNORECASE), ActivityLabel.READING, "tail"),
    # Editing patterns
    (re.compile(r"\bEdit\b", re.IGNORECASE), ActivityLabel.EDITING, "Edit"),
    (re.compile(r"\bWrite\b", re.IGNORECASE), ActivityLabel.EDITING, "Write"),
    (re.compile(r"Editing\s+", re.IGNORECASE), ActivityLabel.EDITING, "Edit"),
    (re.compile(r"Writing\s+", re.IGNORECASE), ActivityLabel.EDITING, "Write"),
    (re.compile(r"\bsed\s+", re.IGNORECASE), ActivityLabel.EDITING, "sed"),
    (re.compile(r"\bawk\s+", re.IGNORECASE), ActivityLabel.EDITING, "awk"),
    # Git operations (considered editing/code work)
    (re.compile(r"\bgit\s+(add|commit|push)", re.IGNORECASE), ActivityLabel.EDITING, "git"),
    # Testing patterns
    (re.compile(r"\bpytest\b", re.IGNORECASE), ActivityLabel.TESTING, "pytest"),
    (re.compile(r"\bnpm\s+test\b", re.IGNORECASE), ActivityLabel.TESTING, "npm test"),
    (re.compile(r"\byarn\s+test\b", re.IGNORECASE), ActivityLabel.TESTING, "yarn test"),
    (re.compile(r"\bpnpm\s+test\b", re.IGNORECASE), ActivityLabel.TESTING, "pnpm test"),
    (re.compile(r"running\s+tests", re.IGNORECASE), ActivityLabel.TESTING, "tests"),
    (re.compile(r"test.*passed", re.IGNORECASE), ActivityLabel.TESTING, "tests"),
    (re.compile(r"test.*failed", re.IGNORECASE), ActivityLabel.TESTING, "tests"),
    (re.compile(r"\bcargo\s+test\b", re.IGNORECASE), ActivityLabel.TESTING, "cargo test"),
    (re.compile(r"\bgo\s+test\b", re.IGNORECASE), ActivityLabel.TESTING, "go test"),
    (re.compile(r"\bmake\s+test\b", re.IGNORECASE), ActivityLabel.TESTING, "make test"),
    (re.compile(r"\bvitest\b", re.IGNORECASE), ActivityLabel.TESTING, "vitest"),
    (re.compile(r"\bjest\b", re.IGNORECASE), ActivityLabel.TESTING, "jest"),
    # Searching patterns
    (re.compile(r"\bGlob\b", re.IGNORECASE), ActivityLabel.SEARCHING, "Glob"),
    (re.compile(r"\bGrep\b", re.IGNORECASE), ActivityLabel.SEARCHING, "Grep"),
    (re.compile(r"\bgrep\s+", re.IGNORECASE), ActivityLabel.SEARCHING, "grep"),
    (re.compile(r"\brg\s+", re.IGNORECASE), ActivityLabel.SEARCHING, "rg"),
    (re.compile(r"\bfind\s+", re.IGNORECASE), ActivityLabel.SEARCHING, "find"),
    (re.compile(r"Searching\s+", re.IGNORECASE), ActivityLabel.SEARCHING, "Search"),
    # Web search
    (re.compile(r"\bWebSearch\b", re.IGNORECASE), ActivityLabel.SEARCHING, "WebSearch"),
    (re.compile(r"\bWebFetch\b", re.IGNORECASE), ActivityLabel.SEARCHING, "WebFetch"),
    # Build patterns (counted as testing for now - building to verify)
    (re.compile(r"\bnpm\s+run\s+build\b", re.IGNORECASE), ActivityLabel.TESTING, "npm build"),
    (re.compile(r"\byarn\s+build\b", re.IGNORECASE), ActivityLabel.TESTING, "yarn build"),
    (re.compile(r"\bcargo\s+build\b", re.IGNORECASE), ActivityLabel.TESTING, "cargo build"),
    (re.compile(r"\bmake\b(?!\s+test)", re.IGNORECASE), ActivityLabel.TESTING, "make"),
]

# Thinking indicators - lower priority, used when no tool is detected
THINKING_INDICATORS = [
    "analyzing",
    "considering",
    "planning",
    "looking at",
    "let me",
    "i'll",
    "i will",
    "first,",
    "next,",
    "then,",
    "now i",
    "examining",
    "reviewing",
    "checking",
]


def detect_activity(line: str) -> ActivityDetection:
    """Detect Claude's current activity from output line.

    Args:
        line: A line of output from Claude

    Returns:
        ActivityDetection with detected activity
    """
    # Check tool patterns first (higher priority)
    for pattern, activity, tool_name in TOOL_PATTERNS:
        if pattern.search(line):
            return ActivityDetection(activity=activity, tool_name=tool_name)

    # Check for thinking indicators
    line_lower = line.lower()
    for indicator in THINKING_INDICATORS:
        if indicator in line_lower:
            return ActivityDetection(activity=ActivityLabel.THINKING)

    return ActivityDetection(activity=None)


class ActivityTracker:
    """Tracks activity across multiple output lines."""

    # Number of lines without detected activity before defaulting to THINKING
    THINKING_THRESHOLD = 5

    def __init__(self):
        """Initialize the activity tracker."""
        self._last_activity: Optional[ActivityLabel] = None
        self._consecutive_none = 0

    def process_line(self, line: str) -> Optional[ActivityLabel]:
        """Process a line and return activity if changed.

        Args:
            line: Line of Claude output

        Returns:
            Activity if it changed, None if unchanged
        """
        detection = detect_activity(line)

        # Log when activity is detected
        if detection.activity:
            self._consecutive_none = 0
            if detection.activity != self._last_activity:
                logger.info(f"Activity changed: {detection.activity.value}")
                self._last_activity = detection.activity
                return detection.activity
        else:
            self._consecutive_none += 1
            # Log sample of unmatched lines for debugging
            if self._consecutive_none <= 3 or self._consecutive_none % 20 == 0:
                logger.debug(f"No activity match ({self._consecutive_none}): {line[:80]}")
            # After threshold lines with no detected activity, assume thinking
            if (
                self._consecutive_none > self.THINKING_THRESHOLD
                and self._last_activity != ActivityLabel.THINKING
            ):
                self._last_activity = ActivityLabel.THINKING
                return ActivityLabel.THINKING

        return None

    def reset(self) -> None:
        """Reset tracker state."""
        self._last_activity = None
        self._consecutive_none = 0
