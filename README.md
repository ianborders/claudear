# Claudiar

Autonomous development automation with Claude Code and Linear.

Claudiar watches your Linear board and automatically picks up tasks when you move them to "Todo". It creates isolated git worktrees, runs Claude Code to implement the work, communicates progress via Linear comments, and creates pull requests when done.

## How It Works

```
1. Move Linear issue → "Todo"
2. Claudiar picks it up automatically
3. Creates git worktree + branch
4. Claude Code works on the task
5. If blocked → posts comment, waits for your response
6. When complete → pushes to GitHub, creates PR, moves to "In Review"
7. You review, move to "Done" → PR auto-merges
```

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         CLAUDIAR                                 │
├─────────────────────────────────────────────────────────────────┤
│  Webhook Server (FastAPI)  →  Task Manager  →  Claude Runner    │
│         ↕                          ↕                ↕           │
│  Linear Client (GraphQL)      Git Worktrees    SQLite Store     │
└─────────────────────────────────────────────────────────────────┘
         ↕                                            ↕
      LINEAR                                       GITHUB
```

## Prerequisites

- Python 3.9+
- [ngrok](https://ngrok.com/) account (free tier works)
- [Claude Code](https://claude.ai/code) CLI installed and authenticated
- Linear workspace with API access
- GitHub CLI (`gh`) installed and authenticated
- A git repository to work on

## Installation

```bash
# Clone the repo
git clone https://github.com/ianborders/claudiar.git
cd claudiar

# Install (creates the `claudiar` command automatically)
pip install -e .

# Copy and configure environment
cp .env.example .env
# Edit .env with your API keys (see Configuration below)
```

> **Note:** If `claudiar` command is not found, add Python's bin directory to your PATH:
> ```bash
> # For macOS/Linux, add to ~/.zshrc or ~/.bashrc:
> export PATH="$HOME/Library/Python/3.9/bin:$PATH"  # macOS
> export PATH="$HOME/.local/bin:$PATH"              # Linux
> ```

## Configuration

Create a `.env` file with:

```bash
# Linear Integration
LINEAR_API_KEY=lin_api_xxx           # Linear API key
LINEAR_WEBHOOK_SECRET=lin_wh_xxx     # Created when registering webhook
LINEAR_TEAM_ID=XXX                   # Your team key (e.g., "ENG")

# Linear Workflow States (match your board column names)
LINEAR_STATE_TODO=Todo
LINEAR_STATE_IN_PROGRESS=In Progress
LINEAR_STATE_IN_REVIEW=In Review
LINEAR_STATE_DONE=Done

# GitHub (for PR creation)
GITHUB_TOKEN=ghp_xxx                 # GitHub personal access token

# Repository to work on
REPO_PATH=/path/to/your/repo         # Absolute path to a git repository

# Server
WEBHOOK_PORT=8000

# ngrok (for webhook tunnel)
NGROK_AUTHTOKEN=xxx                  # ngrok auth token
```

### Getting your API keys

| Key | Where to get it |
|-----|-----------------|
| `LINEAR_API_KEY` | Linear → Settings → API → Personal API keys |
| `LINEAR_TEAM_ID` | Your team's key from the URL (e.g., `ENG` from `linear.app/ENG/...`) |
| `GITHUB_TOKEN` | GitHub → Settings → Developer settings → Personal access tokens |
| `NGROK_AUTHTOKEN` | [ngrok Dashboard](https://dashboard.ngrok.com/get-started/your-authtoken) → Your Authtoken |

## Setup

### 1. Set up ngrok with a static domain

Claudiar manages ngrok automatically, but you need a **static ngrok domain** so the webhook URL persists across restarts.

1. Go to [ngrok Dashboard → Domains](https://dashboard.ngrok.com/cloud-edge/domains)
2. Create a free static domain (e.g., `your-name.ngrok-free.app`)
3. Configure ngrok to use it by creating/editing `~/Library/Application Support/ngrok/ngrok.yml`:
   ```yaml
   authtoken: your_auth_token
   tunnels:
     claudiar:
       addr: 8000
       proto: http
       domain: your-name.ngrok-free.app
   ```

### 2. Register Linear webhook

1. Go to Linear → Settings → API → Webhooks → **Create webhook**
2. Configure:

   | Setting | Value |
   |---------|-------|
   | URL | `https://your-name.ngrok-free.app/webhooks/linear` |
   | Label | `Claudiar` |
   | Team | Select your team |
   | Events | Issues, Comments |

3. Copy the **signing secret** to your `.env` as `LINEAR_WEBHOOK_SECRET`

### 3. Run Claudiar

```bash
claudiar
```

That's it! Claudiar will:
- Start the webhook server on port 8000
- Connect ngrok tunnel automatically
- Begin watching for Linear events

## Usage

1. Create issues in Linear as usual
2. When ready to work on something, move it to **"Todo"**
3. Claudiar automatically:
   - Moves it to "In Progress"
   - Creates a branch: `claudiar/issue-identifier`
   - Starts Claude Code working on it
4. Watch progress in Linear comments
5. If Claude gets blocked, it will ask for help via comment
   - Reply to unblock and continue
6. When complete:
   - Code is pushed to GitHub
   - PR is created
   - Issue moves to "In Review"
7. Review the PR
8. Move issue to **"Done"** → PR auto-merges and branch is deleted

## Task States

```
PENDING → IN_PROGRESS ⟷ BLOCKED → FAILED
              ↓
         COMPLETED → IN_REVIEW → DONE (auto-merge)
```

## Project Structure

```
claudiar/
├── claudiar/
│   ├── main.py              # Entry point
│   ├── config.py            # Settings
│   ├── server/              # FastAPI webhook server
│   ├── linear/              # Linear API client
│   ├── claude/              # Claude Code runner
│   ├── git/                 # Worktree & GitHub integration
│   └── tasks/               # Task orchestration
└── scripts/
    └── test_webhook.py      # Test webhook endpoint
```

## Troubleshooting

### Webhook not receiving events
- Check Claudiar logs show ngrok tunnel established
- Verify webhook URL in Linear matches your ngrok domain
- Verify `LINEAR_WEBHOOK_SECRET` matches what Linear provided
- Test endpoint: `curl https://your-domain.ngrok-free.app/health`

### Claude not starting
- Ensure `claude` CLI is installed: `which claude`
- Ensure you're logged in to Claude Code (run `claude` manually to check)
- Verify `REPO_PATH` exists and is a git repository

### Tasks stuck in "Blocked"
- Check Linear for Claude's comment asking for help
- Reply to the comment to unblock
- Claudiar polls comments every 30 seconds

### Port already in use
- The `claudiar` command automatically kills existing instances
- If issues persist: `lsof -ti:8000 | xargs kill -9`

### ngrok tunnel fails
- Check your `NGROK_AUTHTOKEN` is correct
- Ensure no other ngrok processes: `pkill ngrok`

## How Claude Code is Used

Claudiar runs Claude Code CLI in headless mode using your **Claude Code subscription** (not API credits). It's the same Claude you use interactively, just automated.

The runner:
1. Starts `claude --print --dangerously-skip-permissions`
2. Sends a structured prompt with the issue details
3. Monitors output for completion or blocked states
4. Commits and pushes when done

## License

MIT
