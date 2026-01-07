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
6. When complete → pushes to GitHub, creates PR
7. You review, move to "Done"
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

- Python 3.10+
- [ngrok](https://ngrok.com/) account (free tier works)
- [Claude Code](https://claude.ai/code) CLI installed
- Linear workspace with API access
- GitHub account with personal access token

## Installation

```bash
# Clone the repo
git clone https://github.com/YOUR_USERNAME/claudiar.git
cd claudiar

# Install dependencies
pip install -e .

# Copy and configure environment
cp .env.example .env
# Edit .env with your API keys
```

## Configuration

Create a `.env` file with:

```bash
# Linear Integration
LINEAR_API_KEY=lin_api_xxx           # Settings → API → Personal API keys
LINEAR_WEBHOOK_SECRET=lin_wh_xxx     # Created when registering webhook
LINEAR_TEAM_ID=XXX                   # Team settings → scroll to bottom

# Linear Workflow States (match your board)
LINEAR_STATE_TODO=Todo
LINEAR_STATE_IN_PROGRESS=In Progress
LINEAR_STATE_IN_REVIEW=In Review
LINEAR_STATE_DONE=Done

# GitHub
GITHUB_TOKEN=ghp_xxx                 # Settings → Developer settings → Personal access tokens

# Repository to work on
REPO_PATH=/path/to/your/repo         # Must be a git repository

# Server
WEBHOOK_PORT=8000

# ngrok
NGROK_AUTHTOKEN=xxx                  # dashboard.ngrok.com/get-started/your-authtoken

# Claude
ANTHROPIC_API_KEY=sk-ant-xxx         # console.anthropic.com
```

## Setup

### 1. Start ngrok tunnel

```bash
./start-ngrok.sh
# or: ngrok http 8000
```

Note the public URL (e.g., `https://abc123.ngrok-free.app`)

### 2. Register Linear webhook

Go to Linear → Settings → API → Webhooks → Create webhook:

| Setting | Value |
|---------|-------|
| URL | `https://YOUR-NGROK-URL/webhooks/linear` |
| Label | `Claudiar` |
| Team | Select your team |
| Events | ✅ Issues, ✅ Comments |

Copy the signing secret to your `.env` as `LINEAR_WEBHOOK_SECRET`

### 3. Run Claudiar

```bash
claudiar
```

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
7. Review the PR, merge it
8. Move issue to "Done"

## Task States

```
PENDING → IN_PROGRESS ⟷ BLOCKED → FAILED
              ↓
         COMPLETED → IN_REVIEW → DONE
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
├── scripts/
│   ├── start-ngrok.sh       # Start ngrok tunnel
│   ├── register_webhook.py  # Register Linear webhook
│   └── test_webhook.py      # Test webhook endpoint
└── docs/
    └── IMPLEMENTATION_PLAN.md
```

## Troubleshooting

### Webhook not receiving events
- Check ngrok is running and URL matches Linear webhook config
- Verify `LINEAR_WEBHOOK_SECRET` matches what Linear provided
- Test with: `python scripts/test_webhook.py`

### Claude not starting
- Ensure `claude` CLI is installed and authenticated
- Check `ANTHROPIC_API_KEY` is set correctly
- Verify `REPO_PATH` exists and is a git repository

### Tasks stuck in "Blocked"
- Check Linear for Claude's comment asking for help
- Reply to the comment to unblock
- Claudiar polls comments every 30 seconds

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Format code
black claudiar/
ruff check claudiar/
```

## License

MIT
