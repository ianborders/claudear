# Claudear Implementation

## Overview

Claudear is an autonomous development automation system that bridges Linear project management with Claude Code CLI. When you move a Linear issue to "Todo", Claudear automatically picks it up, creates an isolated git worktree, runs Claude Code to implement the task, and manages the full lifecycle through PR creation.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         CLAUDEAR                                 │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐      │
│  │   FastAPI    │    │    Task      │    │    Claude    │      │
│  │   Webhook    │───>│   Manager    │───>│    Runner    │      │
│  │   Server     │    │              │    │  (CLI)       │      │
│  └──────────────┘    └──────────────┘    └──────────────┘      │
│         ▲                   │                   │               │
│         │                   ▼                   ▼               │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐      │
│  │   Linear     │    │     Git      │    │   SQLite     │      │
│  │   Client     │    │   Worktree   │    │    Store     │      │
│  │  (GraphQL)   │    │   Manager    │    │              │      │
│  └──────────────┘    └──────────────┘    └──────────────┘      │
│         │                                                       │
│         ▼                                                       │
│  ┌──────────────┐                                               │
│  │   Label      │  Real-time activity labels on Linear issues   │
│  │   Manager    │                                               │
│  └──────────────┘                                               │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
         │                                        │
         ▼                                        ▼
   ┌──────────┐                            ┌──────────┐
   │  LINEAR  │                            │  GITHUB  │
   │   API    │                            │   (gh)   │
   └──────────┘                            └──────────┘
```

---

## Key Design Decisions

| Decision | Implementation |
|----------|----------------|
| Language | Python 3.10+ |
| Claude Integration | Claude Code CLI (uses subscription, not API credits) |
| Task Detection | Linear Webhooks (real-time) |
| Webhook Tunnel | ngrok (static domain supported) |
| Concurrency | Parallel via git worktrees |
| Runtime | Local machine |
| Activity Tracking | stream-json output parsing |
| Configuration | .env file in current working directory |

---

## Workflow

```
1. User moves Linear issue → "Todo"
2. Linear webhook → Claudear server (via ngrok)
3. Claudear:
   - Applies "In Progress" label to issue
   - Creates git worktree + branch (claudear/{issue-id})
   - Starts Claude Code CLI session
4. Claude works on task
   - Real-time activity labels (reading, editing, testing, etc.)
   - Progress updates → Linear comments
   - If blocked → Posts comment, waits for response
   - Polls for user comments to unblock
5. When complete:
   - Pushes to GitHub
   - Creates PR (via `gh` CLI)
   - Moves issue → "In Review"
6. User reviews, moves → "Done"
   - PR auto-merges
   - Worktree cleaned up
```

---

## Project Structure

```
claudear/
├── pyproject.toml
├── .env.example
├── docs/
│   └── IMPLEMENTATION_PLAN.md
├── claudear/
│   ├── __init__.py
│   ├── main.py                 # Entry point
│   ├── config.py               # Settings from .env (pydantic-settings)
│   ├── server/
│   │   ├── __init__.py
│   │   ├── app.py              # FastAPI app
│   │   └── routes/
│   │       ├── __init__.py
│   │       └── webhooks.py     # Linear webhook handler
│   ├── linear/
│   │   ├── __init__.py
│   │   ├── client.py           # GraphQL API wrapper
│   │   └── labels.py           # Label management (MajorStateLabel, ActivityLabel)
│   ├── claude/
│   │   ├── __init__.py
│   │   ├── runner.py           # Claude Code CLI execution
│   │   └── activity.py         # Tool-to-activity mapping
│   ├── git/
│   │   ├── __init__.py
│   │   ├── worktree.py         # Worktree management
│   │   └── github.py           # PR creation via gh CLI
│   └── tasks/
│       ├── __init__.py
│       ├── manager.py          # Orchestration
│       └── store.py            # SQLite persistence
└── website/                    # Documentation site (Next.js)
```

---

## Module Details

### Configuration (config.py)

Uses pydantic-settings to load configuration from `.env` file in the current working directory.

```python
class Settings(BaseSettings):
    # Linear Integration
    linear_api_key: str
    linear_webhook_secret: str
    linear_team_id: str  # Team key (e.g., "ENG") or UUID

    # Linear Workflow States
    linear_state_todo: str = "Todo"
    linear_state_in_progress: str = "In Progress"
    linear_state_in_review: str = "In Review"
    linear_state_done: str = "Done"

    # Repository
    repo_path: str
    worktrees_dir: Optional[str] = None  # Defaults to {repo_path}/.worktrees

    # Server
    webhook_port: int = 8000
    webhook_host: str = "0.0.0.0"

    # ngrok
    ngrok_authtoken: str

    # Task Settings
    max_concurrent_tasks: int = 5
    comment_poll_interval: int = 30
    blocked_timeout: int = 3600

    # Labels
    labels_enabled: bool = True
    labels_activity_enabled: bool = True
    labels_debounce_seconds: float = 2.0

    # Logging
    log_level: str = "INFO"
```

**Note:** No `ANTHROPIC_API_KEY` needed - Claudear uses Claude Code CLI which runs on your Claude Code subscription.

---

### Linear Client (linear/client.py)

GraphQL API wrapper for Linear operations.

**Key methods:**
- `get_team_id()` - Resolves team key to UUID
- `get_workflow_states()` - Get state name → ID mapping
- `update_issue_state()` - Move issue to new state
- `add_comment()` - Add comment to issue
- `get_issue_comments()` - Fetch comments for polling
- `create_label()` - Create labels for activity tracking
- `add_label()` / `remove_label()` - Manage issue labels

---

### Label Management (linear/labels.py)

Real-time visual feedback on Linear issues via labels.

**Label Types:**

```python
class MajorStateLabel(str, Enum):
    WORKING = "claudear:working"      # Blue - Claude is active
    BLOCKED = "claudear:blocked"      # Red - Waiting for human input
    REVIEW = "claudear:review"        # Yellow - PR created
    DONE = "claudear:done"            # Green - Completed

class ActivityLabel(str, Enum):
    READING = "claudear:reading"      # Currently reading files
    EDITING = "claudear:editing"      # Writing/editing code
    SEARCHING = "claudear:searching"  # Glob/Grep/WebSearch
    TESTING = "claudear:testing"      # Running tests (Bash)
    THINKING = "claudear:thinking"    # Planning/Task tool
```

**Debouncing:** Activity labels are debounced to prevent excessive API calls. First update is immediate, subsequent updates within the debounce window are skipped.

---

### Claude Runner (claude/runner.py)

Executes Claude Code CLI with streaming JSON output for real-time activity tracking.

**Command construction:**
```python
cmd = [
    "claude",
    "--print",
    "--verbose",  # Required for stream-json with --print
    "--output-format", "stream-json",
    "--dangerously-skip-permissions",
]
```

**Key features:**
- Streams JSONL output line-by-line
- Parses `tool_use` events to detect activity
- Calls `on_tool_use` callback for real-time label updates
- Captures final result message

**Prompt template:**
```
You are working on Linear issue {identifier}: {title}

## Description
{description}

## Instructions
1. Analyze the requirements
2. Implement the solution
3. Write/update tests as needed
4. Ensure all tests pass
5. Commit your changes with a descriptive message

When finished, ensure all changes are committed.
```

---

### Activity Mapping (claude/activity.py)

Maps Claude Code tool names to activity labels.

```python
TOOL_NAME_TO_ACTIVITY: dict[str, ActivityLabel] = {
    "Read": ActivityLabel.READING,
    "Glob": ActivityLabel.SEARCHING,
    "Grep": ActivityLabel.SEARCHING,
    "Edit": ActivityLabel.EDITING,
    "Write": ActivityLabel.EDITING,
    "Bash": ActivityLabel.TESTING,
    "WebSearch": ActivityLabel.SEARCHING,
    "Task": ActivityLabel.THINKING,
}
```

---

### Git Worktree Manager (git/worktree.py)

Creates isolated working directories for parallel task execution.

**Key methods:**
- `create_worktree()` - Creates worktree with branch `claudear/{issue-id}`
- `remove_worktree()` - Cleans up worktree and optionally deletes branch
- `get_worktree_path()` - Returns path for an issue

**Branch naming:** `claudear/{issue-identifier}` (e.g., `claudear/ENG-123`)

---

### GitHub Integration (git/github.py)

PR creation and management via `gh` CLI.

**Key methods:**
- `create_pull_request()` - Creates PR with Linear issue link
- `merge_pull_request()` - Merges PR when issue moved to Done

**PR format:**
```markdown
## Summary
[Issue title]

## Linear Issue
Closes {issue-identifier}

---
🤖 Generated by Claudear
```

---

### Task Manager (tasks/manager.py)

Central orchestration of the task lifecycle.

**Key methods:**
- `handle_issue_update()` - Process webhook events
- `start_task()` - Full task initiation flow
- `check_blocked_tasks()` - Poll for unblock comments
- `cleanup_task()` - Remove worktree on completion

**Concurrency:** Tracks active tasks, limits to `MAX_CONCURRENT_TASKS`.

---

### Task Store (tasks/store.py)

SQLite persistence for crash recovery.

**Schema:**
```sql
CREATE TABLE tasks (
    issue_id TEXT PRIMARY KEY,
    issue_identifier TEXT NOT NULL,
    branch_name TEXT NOT NULL,
    worktree_path TEXT NOT NULL,
    state TEXT NOT NULL,
    blocked_reason TEXT,
    blocked_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
```

---

### Webhook Server (server/app.py, server/routes/webhooks.py)

FastAPI application receiving Linear webhook events.

**Endpoints:**
- `POST /webhooks/linear` - Receive Linear events
- `GET /health` - Health check

**Security:** HMAC-SHA256 signature verification using `LINEAR_WEBHOOK_SECRET`.

---

## Configuration Template (.env.example)

```bash
# Linear Integration
LINEAR_API_KEY=lin_api_xxxxxxxxxxxxx
LINEAR_WEBHOOK_SECRET=whsec_xxxxxxxxxx
LINEAR_TEAM_ID=ENG  # Your team key from URL (linear.app/ENG/...)

# Linear Workflow States (must match your Linear board exactly)
LINEAR_STATE_TODO=Todo
LINEAR_STATE_IN_PROGRESS=In Progress
LINEAR_STATE_IN_REVIEW=In Review
LINEAR_STATE_DONE=Done

# Repository
REPO_PATH=/path/to/your/repo

# Server
WEBHOOK_PORT=8000

# ngrok
NGROK_AUTHTOKEN=xxxxxxxxxxxxxxxxx

# Task Settings (optional)
MAX_CONCURRENT_TASKS=5
COMMENT_POLL_INTERVAL=30
BLOCKED_TIMEOUT=3600

# Labels (optional)
LABELS_ENABLED=true
LABELS_ACTIVITY_ENABLED=true
LABELS_DEBOUNCE_SECONDS=2.0

# Logging (optional)
LOG_LEVEL=INFO
```

---

## Dependencies

```toml
[project]
name = "claudear"
version = "0.1.0"
description = "Autonomous development automation with Claude Code and Linear"
requires-python = ">=3.10"
dependencies = [
    "fastapi>=0.109.0",
    "uvicorn[standard]>=0.25.0",
    "httpx>=0.26.0",
    "pydantic>=2.5.0",
    "pydantic-settings>=2.1.0",
    "aiosqlite>=0.19.0",
    "pyngrok>=7.0.0",
    "python-dotenv>=1.0.0",
]

[project.scripts]
claudear = "claudear.main:main"
```

---

## State Flow

```
                            ┌─────────────┐
                            │    TODO     │  Issue moved to "Todo"
                            └──────┬──────┘
                                   │
                                   ▼ start_task()
                            ┌─────────────┐
                      ┌────>│ IN_PROGRESS │<────┐
                      │     │  (working)  │     │
                      │     └──────┬──────┘     │
                      │            │            │
           resume()   │            │            │ unblocked
                      │            ▼            │
                      │     ┌─────────────┐     │
                      └─────│   BLOCKED   │─────┘
                            │   (blocked) │
                            └─────────────┘
                                   │
                                   │ complete()
                                   ▼
                            ┌─────────────┐
                            │  IN_REVIEW  │  PR created
                            │  (review)   │
                            └──────┬──────┘
                                   │
                                   │ user moves to "Done"
                                   ▼
                            ┌─────────────┐
                            │    DONE     │  PR merged, cleanup
                            │   (done)    │
                            └─────────────┘
```

Labels in parentheses show the `MajorStateLabel` applied at each state.

---

## Activity Tracking

When Claude Code is running, Claudear parses the stream-json output to detect tool usage in real-time:

```
┌─────────────────────────────────────────────────────────────┐
│  Claude Code CLI (stream-json output)                        │
│                                                              │
│  {"type":"tool_use","name":"Read","input":{...}}            │
│  {"type":"tool_use","name":"Edit","input":{...}}            │
│  {"type":"tool_use","name":"Bash","input":{...}}            │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼ parse JSON, extract tool name
┌─────────────────────────────────────────────────────────────┐
│  Activity Mapper                                             │
│                                                              │
│  Read → "reading"                                            │
│  Edit → "editing"                                            │
│  Bash → "testing"                                            │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼ debounced label update
┌─────────────────────────────────────────────────────────────┐
│  Linear Issue                                                │
│                                                              │
│  Labels: [claudear:working] [claudear:testing]              │
└─────────────────────────────────────────────────────────────┘
```

---

## Blocked Detection & Unblock Flow

1. Claude posts comment: "I need help with..."
2. TaskManager detects blocked state, posts formatted comment:
   ```
   🤖 **Claudear is blocked**

   Reason: [reason from Claude]

   Please respond with guidance to continue.
   ```
3. Label changes: `working` → `blocked`
4. Poll Linear comments every 30 seconds
5. When new human comment detected:
   - Resume Claude session with comment as input
   - Label changes: `blocked` → `working`

---

## Installation & Usage

### Prerequisites
- Python 3.10+
- [Claude Code](https://claude.ai/code) CLI installed and authenticated
- [GitHub CLI](https://cli.github.com/) (`gh`) installed and authenticated
- [ngrok](https://ngrok.com/) account (free tier works)
- Linear workspace with API access

### Installation

```bash
# 1. Clone the repository
git clone https://github.com/ianborders/claudear.git
cd claudear

# 2. Install the claudear command
pip install claudear

# 3. Create your config
cp .env.example .env
# Edit .env with your values
```

### Running

```bash
# Always run from the cloned repo directory
cd claudear
claudear
```

Claudear will:
1. Start the webhook server
2. Create an ngrok tunnel
3. Register the webhook with Linear (first run)
4. Begin listening for issue updates

### Usage

| Action | Result |
|--------|--------|
| Move issue **Backlog → Todo** | Claudear starts working |
| Claude gets stuck | Posts comment, waits for reply |
| Reply to comment | Claudear resumes |
| Task complete | PR created, issue → "In Review" |
| Move issue → **Done** | PR merges, worktree cleaned up |

---

## Finding Your LINEAR_TEAM_ID

Your team key is the short identifier (2-4 characters) that appears in Linear URLs.

**From any Linear URL:**
- `linear.app/ENG/issue/ENG-123` → team key is `ENG`
- `linear.app/CLA/board` → team key is `CLA`

The team key is the segment right after `linear.app/`.

**Note:** You can use either the team key (like `ENG`) or the full UUID. Claudear automatically resolves team keys to UUIDs via the Linear API.
