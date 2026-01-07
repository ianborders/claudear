# Claudear

Autonomous development automation with Claude Code and Linear.

Move a Linear issue from Backlog to "Todo" and Claudear takes over — it creates an isolated git worktree, runs Claude Code to implement the work, posts progress updates, and opens a PR when done. Move to "Done" and the PR auto-merges.

## Installation

### Option 1: pip (Recommended)

```bash
pip install claudear
```

### Option 2: From Source

```bash
git clone https://github.com/ianborders/claudear.git
cd claudear
pip install -e .
```

## Quick Start

1. **Create your config file** at `~/.config/claudear/.env` (see [Configuration](#configuration) below)

2. **Start watching for tasks:**
   ```bash
   claudear
   ```

## How It Works

1. **Move issue from Backlog → Todo** — Claudear picks it up
2. **Automatic implementation** — Creates isolated git worktree, runs Claude Code
3. **Progress updates** — Comments on Linear as it works
4. **Blocked?** — Posts a comment asking for help, waits for your reply
5. **Complete** — Pushes code, creates PR, moves to "In Review"
6. **Move to "Done"** — PR auto-merges, worktree cleaned up

## Prerequisites

- Python 3.9+
- [Claude Code](https://claude.ai/code) CLI installed and authenticated
- [ngrok](https://ngrok.com/) account (free tier works)
- [GitHub CLI](https://cli.github.com/) (`gh`) installed and authenticated
- Linear workspace with API access
- Linear workflow with these states: **Backlog → Todo → In Progress → In Review → Done**

## Configuration

Create a `.env` file:

```bash
# Linear
LINEAR_API_KEY=lin_api_xxx           # Settings → API → Personal API keys
LINEAR_WEBHOOK_SECRET=whsec_xxx      # Created when you register the webhook
LINEAR_TEAM_ID=KYB                   # Your team key from URL (linear.app/KYB/...)

# Required Linear workflow states (must match exactly)
LINEAR_STATE_TODO=Todo
LINEAR_STATE_IN_PROGRESS=In Progress
LINEAR_STATE_IN_REVIEW=In Review
LINEAR_STATE_DONE=Done
# Note: Your Linear board must have: Backlog → Todo → In Progress → In Review → Done

# GitHub
GITHUB_TOKEN=ghp_xxx                 # Settings → Developer settings → Tokens

# Repository
REPO_PATH=/path/to/your/repo         # The repo Claudear will work on

# Server
WEBHOOK_PORT=8000

# ngrok
NGROK_AUTHTOKEN=xxx                  # dashboard.ngrok.com → Your Authtoken
```

## Setup

### 1. Create a static ngrok domain

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

### 4. Run

```bash
claudear
```

Claudear starts the webhook server and connects ngrok automatically.

## Usage

| Action | Result |
|--------|--------|
| Move issue **Backlog → Todo** | Claudear starts working |
| Claude gets stuck | Posts comment, waits for your reply |
| Reply to comment | Claudear resumes |
| Task complete | PR created, issue → "In Review" |
| Move issue → **Done** | PR merges, worktree cleaned up |

## Troubleshooting

**Webhook not receiving events**
- Verify webhook URL matches your ngrok domain
- Check signing secret matches `LINEAR_WEBHOOK_SECRET`
- Test: `curl https://your-domain.ngrok-free.app/health`

**Claude not starting**
- Run `claude` manually to verify CLI is installed and authenticated
- Check `REPO_PATH` exists and is a git repository

**Tasks stuck in "Blocked"**
- Check Linear for Claude's comment asking for help
- Reply to unblock (polls every 30 seconds)

**Port 8000 in use**
- Kill existing processes: `lsof -ti:8000 | xargs kill -9`
- Kill ngrok: `pkill ngrok`

## How It Uses Claude Code

Claudear runs Claude Code CLI in headless mode using your **Claude Code subscription** (not API credits). It's the same Claude you use interactively, just automated.

## License

MIT
