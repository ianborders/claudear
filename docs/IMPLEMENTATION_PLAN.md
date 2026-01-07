# Claudear Implementation Plan

## Overview

Claudear is an autonomous development automation system that bridges Linear project management with Claude Code. When you move a Linear issue to "Todo", Claudear automatically picks it up, creates an isolated git worktree, runs Claude Code to implement the task, and manages the full lifecycle through PR creation.

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
│  │   Server     │    │              │    │  (Agent SDK) │      │
│  └──────────────┘    └──────────────┘    └──────────────┘      │
│         ▲                   │                   │               │
│         │                   ▼                   ▼               │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐      │
│  │   Linear     │    │     Git      │    │   SQLite     │      │
│  │   Client     │    │   Worktree   │    │    Store     │      │
│  │  (GraphQL)   │    │   Manager    │    │              │      │
│  └──────────────┘    └──────────────┘    └──────────────┘      │
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

## User Choices

| Decision | Choice |
|----------|--------|
| Language | Python (Claude Agent SDK) |
| Task Detection | Linear Webhooks |
| Webhook Tunnel | ngrok |
| Concurrency | Parallel via git worktrees |
| Runtime | Local machine |

---

## Workflow

```
1. User moves Linear issue → "Todo"
2. Linear webhook → Claudear server (via ngrok)
3. Claudear:
   - Moves issue → "In Progress"
   - Creates git worktree + branch
   - Starts Claude Code session
4. Claude works on task
   - Progress updates → Linear comments
   - If blocked → Posts comment, waits for response
   - Polls for user comments to unblock
5. When complete:
   - Pushes to GitHub
   - Moves issue → "In Review"
   - Creates PR (via `gh` CLI)
6. User reviews, moves → "Done"
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
│   ├── config.py               # Settings from .env
│   ├── server/
│   │   ├── __init__.py
│   │   ├── app.py              # FastAPI app
│   │   └── routes/
│   │       ├── __init__.py
│   │       └── webhooks.py     # Linear webhook handler
│   ├── linear/
│   │   ├── __init__.py
│   │   ├── client.py           # GraphQL API wrapper
│   │   └── models.py           # Pydantic models
│   ├── claude/
│   │   ├── __init__.py
│   │   ├── runner.py           # Agent SDK session manager
│   │   └── hooks.py            # Blocked detection hooks
│   ├── git/
│   │   ├── __init__.py
│   │   ├── worktree.py         # Worktree management
│   │   └── github.py           # PR creation via gh
│   └── tasks/
│       ├── __init__.py
│       ├── manager.py          # Orchestration
│       ├── state.py            # State machine
│       └── store.py            # SQLite persistence
└── scripts/
    ├── setup_ngrok.py          # ngrok tunnel setup
    └── register_webhook.py     # Linear webhook registration
```

---

## Step-by-Step Implementation Plan

### Step 1: Project Setup
**Files to create:**
- `pyproject.toml` - Project configuration and dependencies
- `.env.example` - Template for environment variables
- `.gitignore` - Ignore .env, __pycache__, etc.
- `claudear/__init__.py` - Package init

**Actions:**
1. Create project structure directories
2. Define dependencies (fastapi, httpx, pydantic, etc.)
3. Set up Python virtual environment

---

### Step 2: Configuration Module
**Files to create:**
- `claudear/config.py` - Settings class using pydantic-settings

**Configuration needed:**
```python
# Linear
LINEAR_API_KEY
LINEAR_WEBHOOK_SECRET
LINEAR_TEAM_ID
LINEAR_STATE_TODO / IN_PROGRESS / IN_REVIEW / DONE

# GitHub
GITHUB_TOKEN

# Repository
REPO_PATH
WORKTREES_DIR

# Server
WEBHOOK_PORT
WEBHOOK_HOST

# ngrok
NGROK_AUTHTOKEN

# Claude
ANTHROPIC_API_KEY
```

---

### Step 3: Linear Client
**Files to create:**
- `claudear/linear/__init__.py`
- `claudear/linear/models.py` - Pydantic models for Linear entities
- `claudear/linear/client.py` - GraphQL API wrapper

**Key methods:**
1. `get_workflow_states(team_id)` - Get state name → ID mapping
2. `update_issue_state(issue_id, state_name)` - Move issue to new state
3. `post_comment(issue_id, body)` - Add comment to issue
4. `get_comments_since(issue_id, timestamp)` - Poll for new comments

---

### Step 4: Git Worktree Manager
**Files to create:**
- `claudear/git/__init__.py`
- `claudear/git/worktree.py` - Worktree operations

**Key methods:**
1. `create(branch_name, issue_identifier)` - Create new worktree
2. `remove(issue_identifier)` - Clean up worktree
3. `list_worktrees()` - List active worktrees

**Branch naming:** `claudear/{issue-identifier}` (e.g., `claudear/ENG-123`)

---

### Step 5: GitHub Integration
**Files to create:**
- `claudear/git/github.py` - PR creation via gh CLI

**Key methods:**
1. `push_branch(worktree_path, branch_name)` - Git push
2. `create_pr(branch_name, title, body, base_branch)` - gh pr create
3. `link_to_linear(pr_url, issue_identifier)` - Add Linear link to PR body

---

### Step 6: Task State Machine
**Files to create:**
- `claudear/tasks/__init__.py`
- `claudear/tasks/state.py` - TaskState enum and StateMachine class

**States:**
```
PENDING → IN_PROGRESS ⟷ BLOCKED → FAILED
              ↓
         COMPLETED → IN_REVIEW → DONE
```

**Valid transitions:**
- PENDING → IN_PROGRESS
- IN_PROGRESS → BLOCKED, COMPLETED, FAILED
- BLOCKED → IN_PROGRESS, FAILED
- COMPLETED → IN_REVIEW
- IN_REVIEW → DONE, IN_PROGRESS (re-review)

---

### Step 7: Task Store (Persistence)
**Files to create:**
- `claudear/tasks/store.py` - SQLite persistence

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

**Key methods:**
1. `init()` - Create schema
2. `save_task(task)` - Insert/update task
3. `get_task(issue_id)` - Retrieve task
4. `get_blocked_tasks()` - Find blocked tasks for polling

---

### Step 8: Claude Runner
**Files to create:**
- `claudear/claude/__init__.py`
- `claudear/claude/runner.py` - Agent SDK session manager
- `claudear/claude/hooks.py` - Custom hooks

**Key functionality:**
1. Build prompt from Linear issue (title, description)
2. Start Claude Agent SDK session with allowed tools
3. Detect "BLOCKED:" in output → pause, post comment
4. Detect "TASK_COMPLETE" → mark complete
5. Resume session with user input after unblock

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

If blocked, say: "BLOCKED: [reason]"
When complete, say: "TASK_COMPLETE"
```

---

### Step 9: Task Manager (Orchestrator)
**Files to create:**
- `claudear/tasks/manager.py` - Central orchestration

**Key methods:**
1. `start_task(issue)` - Full task initiation flow
2. `handle_blocked(issue, reason)` - Post comment, update state
3. `handle_unblock(issue_id, comment)` - Resume Claude session
4. `handle_complete(issue)` - Push, create PR, update Linear
5. `poll_blocked_comments()` - Background task for unblock detection

**Concurrency:**
- Track active tasks in dict: `{issue_id: ActiveTask}`
- Limit concurrent tasks (configurable, default 5)
- Queue pending tasks when limit reached

---

### Step 10: Webhook Server
**Files to create:**
- `claudear/server/__init__.py`
- `claudear/server/app.py` - FastAPI application
- `claudear/server/routes/__init__.py`
- `claudear/server/routes/webhooks.py` - Linear webhook endpoint

**Endpoints:**
- `POST /webhooks/linear` - Receive Linear events
- `GET /health` - Health check

**Security:**
- HMAC-SHA256 signature verification
- Validate Linear-Signature header

**Webhook handling:**
1. Verify signature
2. Parse payload
3. Check if issue moved to "Todo"
4. Dispatch to TaskManager.start_task() (background task)

---

### Step 11: Main Entry Point
**Files to create:**
- `claudear/main.py` - Application startup

**Startup sequence:**
1. Load configuration
2. Initialize TaskStore (create DB schema)
3. Initialize components (LinearClient, WorktreeManager, TaskManager)
4. Start ngrok tunnel (via pyngrok)
5. Register webhook with Linear (if not exists)
6. Start background tasks (comment polling)
7. Run FastAPI server (uvicorn)

---

### Step 12: Setup Scripts
**Files to create:**
- `scripts/setup_ngrok.py` - ngrok tunnel helper
- `scripts/register_webhook.py` - One-time Linear webhook setup

**ngrok setup:**
```python
from pyngrok import ngrok
tunnel = ngrok.connect(8000, "http")
print(f"Webhook URL: {tunnel.public_url}/webhooks/linear")
```

**Webhook registration:**
```graphql
mutation CreateWebhook($url: String!, $teamId: String!) {
    webhookCreate(input: {
        url: $url,
        teamId: $teamId,
        resourceTypes: ["Issue"]
    }) {
        success
        webhook { id url }
    }
}
```

---

## Configuration Template (.env.example)

```bash
# Linear Integration
LINEAR_API_KEY=lin_api_xxxxxxxxxxxxx
LINEAR_WEBHOOK_SECRET=whsec_xxxxxxxxxx
LINEAR_TEAM_ID=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx

# Linear Workflow States (customize to your board)
LINEAR_STATE_TODO=Todo
LINEAR_STATE_IN_PROGRESS=In Progress
LINEAR_STATE_IN_REVIEW=In Review
LINEAR_STATE_DONE=Done

# GitHub
GITHUB_TOKEN=ghp_xxxxxxxxxxxxxxxxxxxx

# Repository
REPO_PATH=/path/to/your/repo
WORKTREES_DIR=/path/to/worktrees

# Server
WEBHOOK_PORT=8000
WEBHOOK_HOST=0.0.0.0

# ngrok
NGROK_AUTHTOKEN=xxxxxxxxxxxxxxxxx

# Claude
ANTHROPIC_API_KEY=sk-ant-xxxxxxxxxxxxx

# Task Settings
MAX_CONCURRENT_TASKS=5
COMMENT_POLL_INTERVAL=30
BLOCKED_TIMEOUT=3600

# Logging
LOG_LEVEL=INFO
```

---

## Dependencies (pyproject.toml)

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

[project.optional-dependencies]
dev = [
    "pytest>=7.4.0",
    "pytest-asyncio>=0.23.0",
    "black>=23.12.0",
    "ruff>=0.1.9",
]

[project.scripts]
claudear = "claudear.main:main"
```

---

## Implementation Phases

### Phase 1: MVP (Steps 1-12)
- Single task end-to-end flow
- Basic blocked detection (keyword matching)
- In-memory task tracking
- Manual ngrok setup

### Phase 2: Enhanced
- Concurrent tasks (multiple worktrees)
- SQLite persistence for crash recovery
- Session resume after user responds
- Automatic ngrok tunnel via pyngrok
- Progress comments to Linear

### Phase 3: Production
- Advanced blocked detection (hooks, stall detection)
- Task queue with priority
- Docker containerization
- Monitoring dashboard
- Rate limiting

---

## State Machine Diagram

```
                            ┌─────────────┐
                            │   PENDING   │  Issue moved to "Todo"
                            └──────┬──────┘
                                   │
                                   ▼ start_task()
                            ┌─────────────┐
                      ┌────>│ IN_PROGRESS │<────┐
                      │     └──────┬──────┘     │
                      │            │            │
           resume()   │            │            │ unblocked
                      │            ▼            │
                      │     ┌─────────────┐     │
                      └─────│   BLOCKED   │─────┘
                            └─────────────┘
                                   │
                                   │ timeout / give up
                                   ▼
                            ┌─────────────┐
                      ┌─────│   FAILED    │
                      │     └─────────────┘
                      │
                      │            │ complete()
                      │            ▼
                      │     ┌─────────────┐
                      │     │  COMPLETED  │
                      │     └──────┬──────┘
                      │            │
                      │            │ push & create PR
                      │            ▼
                      │     ┌─────────────┐
                      └────>│  IN_REVIEW  │
                            └──────┬──────┘
                                   │
                                   │ user moves to "Done"
                                   ▼
                            ┌─────────────┐
                            │    DONE     │
                            └─────────────┘
```

---

## Blocked Detection Strategies

### 1. Keyword Matching
```python
BLOCKED_PATTERNS = [
    r"BLOCKED:",
    r"I need clarification",
    r"I cannot proceed",
    r"permission denied",
    r"access denied",
]
```

### 2. Tool Output Analysis
- Check Bash command failures
- Detect permission errors
- Notice missing files/dependencies

### 3. Stall Detection
- No tool activity for 5+ minutes
- Ask Claude to report status

---

## Unblock Flow

1. Claude detects blocker, outputs "BLOCKED: [reason]"
2. TaskManager catches this, posts comment to Linear:
   ```
   🤖 **Claudear is blocked**

   Reason: [reason]

   Please respond with guidance to continue.
   ```
3. Poll Linear comments every 30 seconds
4. When new human comment detected:
   - Transition state: BLOCKED → IN_PROGRESS
   - Resume Claude session with comment as input
   - Continue working

---

## PR Creation Format

```bash
gh pr create \
  --title "feat(ENG-123): [Issue title]" \
  --body "## Summary
Implements [issue title]

## Linear Issue
Closes ENG-123

## Changes
- [Auto-generated from commit messages]

---
🤖 Generated by Claudear" \
  --base main
```

---

## Next Steps After Implementation

1. Create Linear project with Kanban board
2. Configure workflow states (Todo, In Progress, In Review, Done)
3. Set up target repository
4. Fill in .env with API keys
5. Run `claudear` to start server
6. Move an issue to "Todo" and watch Claudear work!
