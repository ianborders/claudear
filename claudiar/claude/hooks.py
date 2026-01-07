"""Hook definitions for Claude Code sessions."""

import re
from dataclasses import dataclass
from typing import Callable, Optional

# Patterns that indicate Claude is blocked
BLOCKED_PATTERNS = [
    r"BLOCKED:",
    r"I need clarification",
    r"I cannot proceed",
    r"I need more information",
    r"Could you clarify",
    r"I'm not sure",
    r"permission denied",
    r"access denied",
    r"missing information",
    r"unclear requirement",
    r"waiting for input",
    r"need your guidance",
]

# Patterns that indicate task completion
COMPLETION_PATTERNS = [
    r"TASK_COMPLETE",
    r"task is complete",
    r"successfully completed",
    r"all done",
    r"finished implementing",
    r"implementation complete",
]


@dataclass
class BlockedDetection:
    """Result of blocked detection."""

    is_blocked: bool
    reason: Optional[str] = None
    pattern_matched: Optional[str] = None


@dataclass
class CompletionDetection:
    """Result of completion detection."""

    is_complete: bool
    pattern_matched: Optional[str] = None


def detect_blocked(text: str) -> BlockedDetection:
    """Detect if Claude is blocked based on output text.

    Args:
        text: Output text from Claude

    Returns:
        BlockedDetection with results
    """
    for pattern in BLOCKED_PATTERNS:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            # Extract reason from text around the match
            reason = _extract_reason(text, match, pattern)
            return BlockedDetection(
                is_blocked=True,
                reason=reason,
                pattern_matched=pattern,
            )

    return BlockedDetection(is_blocked=False)


def detect_completion(text: str) -> CompletionDetection:
    """Detect if Claude has completed the task.

    Args:
        text: Output text from Claude

    Returns:
        CompletionDetection with results
    """
    for pattern in COMPLETION_PATTERNS:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return CompletionDetection(
                is_complete=True,
                pattern_matched=pattern,
            )

    return CompletionDetection(is_complete=False)


def _extract_reason(text: str, match: re.Match, pattern: str) -> str:
    """Extract the reason for blocking from the surrounding text.

    Args:
        text: Full text
        match: Regex match object
        pattern: Pattern that matched

    Returns:
        Extracted reason string
    """
    # Get text after the match
    start = match.end()
    remaining = text[start:].strip()

    # If pattern was "BLOCKED:", get the text after it
    if "BLOCKED:" in pattern.upper():
        # Take text until next sentence or newline
        end_match = re.search(r"[.!?\n]", remaining)
        if end_match:
            return remaining[: end_match.start()].strip()
        return remaining[:200].strip()  # Limit length

    # For other patterns, use the surrounding context
    context_start = max(0, match.start() - 50)
    context_end = min(len(text), match.end() + 150)
    context = text[context_start:context_end].strip()

    # Clean up the context
    context = re.sub(r"\s+", " ", context)
    return context


def build_prompt(
    issue_identifier: str,
    title: str,
    description: Optional[str] = None,
    additional_context: Optional[str] = None,
) -> str:
    """Build the initial prompt for Claude.

    Args:
        issue_identifier: Issue identifier (e.g., "ENG-123")
        title: Issue title
        description: Issue description
        additional_context: Any additional context

    Returns:
        Formatted prompt string
    """
    prompt_parts = [
        f"You are working on Linear issue {issue_identifier}: {title}",
        "",
        "## Description",
        description or "No description provided.",
        "",
    ]

    if additional_context:
        prompt_parts.extend(
            [
                "## Additional Context",
                additional_context,
                "",
            ]
        )

    prompt_parts.extend(
        [
            "## Instructions",
            "1. Analyze the requirements carefully",
            "2. Explore the codebase to understand the existing patterns",
            "3. Implement the solution following existing conventions",
            "4. Write or update tests as needed",
            "5. Ensure all tests pass",
            "6. Commit your changes with a descriptive message",
            "",
            "## Communication",
            "- If you encounter any blockers or need clarification, clearly state:",
            '  "BLOCKED: [specific reason and question]"',
            "- When you have completed the task, state:",
            '  "TASK_COMPLETE"',
            "",
            "Begin by exploring the codebase to understand the structure.",
        ]
    )

    return "\n".join(prompt_parts)


def build_resume_prompt(user_input: str) -> str:
    """Build a prompt to resume after receiving user input.

    Args:
        user_input: The user's clarification/input

    Returns:
        Formatted prompt string
    """
    return f"""The user has provided the following clarification:

{user_input}

Please continue with the task, taking this input into account."""
