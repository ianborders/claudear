# Claudear

Autonomous development automation with Claude Code, Linear, and Notion.

Move a task to "Todo" in Linear or Notion and Claudear takes over — it creates an isolated git worktree, runs Claude Code to implement the work, posts progress updates, and opens a PR when done. Move to "Done" and the PR auto-merges.

[![Clotion](https://img.shields.io/badge/Notion_Support-via_Clotion-black?logo=notion)](https://github.com/ianborders/clotion)

## Features

- **Multi-Provider**: Works with Linear (webhooks) and Notion (polling)
- **Multi-Team/Database**: Support multiple Linear teams or Notion databases simultaneously
- **Per-Project Repos**: Each team/database can have its own repository
- **Parallel Execution**: Run multiple Claude Code sessions concurrently
- **Auto PR Creation**: Pushes code and creates PRs automatically
- **Auto PR Merge**: Move to "Done" to merge PRs
- **Progress Updates**: Posts comments as Claude works

## Installation

```bash
# 1. Clone the repository
git clone https://github.com/ianborders/claudear.git
cd claudear

# 2. Install the claudear command
pip install claudear

# 3. Create your config
cp .env.example .env
```

Edit `.env` with your API keys (see [Configuration](#configuration) below).

### Updating

```bash
pip install -U claudear
```

## Quick Start

Start Claudear from the cloned directory:

```bash
cd claudear
claudear
```

> **Important:** Always run `claudear` from the cloned repository directory. Configuration is loaded from `.env` in the current working directory.

## How It Works

1. **Move task to Todo** — Claudear picks it up
2. **Automatic implementation** — Creates isolated git worktree, runs Claude Code
3. **Progress updates** — Comments on Linear/Notion as it works
4. **Blocked?** — Posts a comment asking for help, waits for your reply
5. **Complete** — Pushes code, creates PR, moves to "In Review"
6. **Move to "Done"** — PR auto-merges, worktree cleaned up

## Prerequisites

- Python 3.9+
- [Claude Code](https://claude.ai/code) CLI installed and authenticated
- [ngrok](https://ngrok.com/) account (free tier works) — for Linear webhooks
- [GitHub CLI](https://cli.github.com/) (`gh`) installed and authenticated
- Linear workspace with API access, and/or Notion workspace with API access

## Configuration

### Single Linear Team (Simplest Setup)

```bash
# Linear
LINEAR_API_KEY=lin_api_xxx           # Settings → API → Personal API keys
LINEAR_WEBHOOK_SECRET=whsec_xxx      # Created when you register the webhook
LINEAR_TEAM_ID=ENG                   # Your team key from URL (linear.app/ENG/...)

# Linear workflow states (must match exactly)
LINEAR_STATE_TODO=Todo
LINEAR_STATE_IN_PROGRESS=In Progress
LINEAR_STATE_IN_REVIEW=In Review
LINEAR_STATE_DONE=Done

# GitHub
GITHUB_TOKEN=ghp_xxx                 # Settings → Developer settings → Tokens

# Repository
REPO_PATH=/path/to/your/repo         # The repo Claudear will work on

# Server & ngrok
WEBHOOK_PORT=8000
NGROK_AUTHTOKEN=xxx                  # dashboard.ngrok.com → Your Authtoken
```

### Multiple Linear Teams

```bash
LINEAR_API_KEY=lin_api_xxx
LINEAR_WEBHOOK_SECRET=whsec_xxx
LINEAR_TEAM_IDS=ENG,INFRA,DESIGN     # Comma-separated team keys

# Per-team repository paths
LINEAR_ENG_REPO=/path/to/engineering-repo
LINEAR_INFRA_REPO=/path/to/infrastructure-repo
LINEAR_DESIGN_REPO=/path/to/design-system-repo
```

### Single Notion Database

```bash
NOTION_API_KEY=secret_xxx
NOTION_DATABASE_ID=abc123def456
NOTION_POLL_INTERVAL=5               # Seconds between polls

REPO_PATH=/path/to/your/repo
GITHUB_TOKEN=ghp_xxx
```

### Multiple Notion Databases

```bash
NOTION_API_KEY=secret_xxx
NOTION_DATABASE_IDS=abc123,def456,ghi789

# Per-database repository paths
NOTION_abc123_REPO=/path/to/project-alpha-repo
NOTION_def456_REPO=/path/to/project-beta-repo
NOTION_ghi789_REPO=/path/to/project-gamma-repo
```

### Both Linear and Notion

Configure both providers — Claudear auto-detects and runs them simultaneously.

## Setup

### 1. Create a static ngrok domain (for Linear)

You need a persistent URL so the Linear webhook survives restarts.

1. Go to [ngrok Domains](https://dashboard.ngrok.com/cloud-edge/domains)
2. Create a free static domain (e.g., `your-name.ngrok-free.app`)
3. Create `~/Library/Application Support/ngrok/ngrok.yml`:

```yaml
authtoken: your_auth_token
tunnels:
  claudear:
    addr: 8000
    proto: http
    domain: your-name.ngrok-free.app
```

### 2. Disable Linear's GitHub automations

Linear has built-in automations that conflict with Claudear. **You must disable them:**

1. Linear → Settings → Team Settings → Workflow → **GitHub**
2. Set all "Automate state changes" options to **No action**
   - "When a branch is created" → No action
   - "When a PR is opened" → No action
   - "When a PR is merged" → No action
   - etc.

If you skip this, Linear will fight Claudear for control of issue states.

### 3. Register Linear webhook

1. Linear → Settings → API → Webhooks → **Create webhook**
2. Configure:
   - **URL**: `https://your-name.ngrok-free.app/webhooks/linear`
   - **Events**: Issues, Comments
3. Copy the **signing secret** to `.env` as `LINEAR_WEBHOOK_SECRET`

### 4. Set up Notion integration (if using Notion)

1. Go to [Notion Integrations](https://www.notion.so/my-integrations)
2. Create a new integration with read/write access
3. Copy the **Internal Integration Token** to `.env` as `NOTION_API_KEY`
4. Share your database with the integration (click "..." → Add connections)

### 5. Run

```bash
claudear
```

Claudear starts the webhook server, connects ngrok (for Linear), and begins polling (for Notion).

## Usage

| Action | Result |
|--------|--------|
| Move task → **Todo** | Claudear starts working |
| Claude gets stuck | Posts comment, waits for your reply |
| Reply to comment | Claudear resumes |
| Task complete | PR created, task → "In Review" |
| Move task → **Done** | PR merges, worktree cleaned up |

## Troubleshooting

**Webhook not receiving events (Linear)**
- Verify webhook URL matches your ngrok domain
- Check signing secret matches `LINEAR_WEBHOOK_SECRET`
- Test: `curl https://your-domain.ngrok-free.app/health`

**Notion tasks not picked up**
- Verify database is shared with your integration
- Check `NOTION_DATABASE_ID` matches the ID in the URL
- Increase `NOTION_POLL_INTERVAL` if rate limited

**Claude not starting**
- Run `claude` manually to verify CLI is installed and authenticated
- Check `REPO_PATH` (or per-team/database paths) exists and is a git repository

**Tasks stuck in "Blocked"**
- Check Linear/Notion for Claude's comment asking for help
- Reply to unblock (polls every 30 seconds)

**Port 8000 in use**
- Kill existing processes: `lsof -ti:8000 | xargs kill -9`
- Kill ngrok: `pkill ngrok`

**Test the multi-provider setup**
```bash
python -m claudear.scripts.test_multi_provider
```

## Migration from Single-Provider

If you're upgrading from an earlier version with existing task data:

```bash
python -m claudear.scripts.migrate_db --dry-run     # Preview changes
python -m claudear.scripts.migrate_db               # Apply migration
```

## How It Uses Claude Code

Claudear runs Claude Code CLI in headless mode using your **Claude Code subscription** (not API credits). It's the same Claude you use interactively, just automated.

## License

MIT
