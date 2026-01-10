# Claudear Multi-Provider Architecture Plan

## Implementation Status

| Phase | Status | Description |
|-------|--------|-------------|
| Phase 1 | ✅ Complete | Core abstractions (types, store, interfaces) |
| Phase 2 | ✅ Complete | Linear provider with multi-team support |
| Phase 3 | ✅ Complete | Notion provider with multi-database support |
| Phase 4 | ✅ Complete | Unified TaskOrchestrator |
| Phase 5 | ✅ Complete | Unified entry point with auto-detection |
| Phase 6 | ✅ Complete | Database migration and backward compatibility |
| Phase 7 | ✅ Complete | Testing and documentation |

**Implemented Files:**
- `claudear/core/types.py` - Unified types (TaskId, ProviderInstance, etc.)
- `claudear/core/state.py` - TaskState and TaskStateMachine
- `claudear/core/store.py` - Multi-provider TaskStore
- `claudear/core/orchestrator.py` - TaskOrchestrator for multi-provider routing
- `claudear/core/config.py` - MultiProviderSettings with auto-detection
- `claudear/core/app.py` - ClaudearApp unified application
- `claudear/providers/base.py` - PMProvider and EventSource ABCs
- `claudear/providers/linear/` - LinearProvider, LinearWebhookEventSource
- `claudear/providers/notion/` - NotionProvider, NotionPollerEventSource
- `claudear/events/types.py` - Unified event types
- `claudear/server/unified_app.py` - Unified FastAPI server
- `claudear/server/routes/unified_webhooks.py` - Multi-team webhook routing
- `claudear/unified_main.py` - New unified entry point
- `claudear/scripts/migrate_db.py` - Database migration script
- `claudear/scripts/test_multi_provider.py` - Test suite

---

## Overview

This document outlines the plan to merge Clotion (Notion integration) into Claudear, creating a unified multi-provider project management automation system. The architecture supports:

- **Multiple providers**: Linear, Notion, and future providers (Jira, Asana, GitHub Projects)
- **Multiple instances per provider**: Multiple Linear teams and/or Notion databases simultaneously
- **Single command**: All managed through the `claudear` command

---

## Current State

### Claudear (Linear)
- **Location**: `/Users/ianwinscom/claudear`
- **Event Model**: Webhooks via FastAPI server
- **API**: Linear GraphQL
- **Activity Tracking**: Linear labels
- **Multi-team**: Partially supported (team_id stored, per-team caching exists)

### Clotion (Notion)
- **Location**: `/Users/ianwinscom/clotion`
- **Event Model**: Polling (5-second intervals)
- **API**: Notion REST
- **Activity Tracking**: Notion rich text properties
- **Multi-database**: Partially supported (database_id stored in TaskRecord)

### Code Overlap (~75%)
| Module | Similarity | Notes |
|--------|------------|-------|
| `tasks/state.py` | 100% | Identical TaskStateMachine |
| `git/github.py` | 98% | Same GitHub PR operations |
| `git/worktree.py` | 95% | Same worktree management |
| `claude/runner.py` | 95% | Same Claude CLI execution |
| `claude/hooks.py` | 90% | Same blocked/completion detection |
| `tasks/store.py` | 90% | Different field names only |

---

## Multi-Team / Multi-Database Analysis

### Linear API Multi-Team Capabilities

| Aspect | API Support | Current Implementation |
|--------|-------------|------------------------|
| Single API key for all teams | ✅ Yes | ✅ Works |
| Per-team webhook subscriptions | ✅ Same URL, same secret, different teamId | ❌ Only registers one team |
| Team identification in webhook | ✅ `teamId` in payload | ✅ Already extracted |
| Per-team state/label caching | ✅ API supports | ✅ Already implemented |
| State `type` field for detection | ✅ `"unstarted"`, `"started"`, `"completed"` | ❌ Not used yet |

**Key insight**: Linear states have a `type` field that's consistent across teams. We can use this instead of matching by name, avoiding per-team state configuration.

### Notion API Multi-Database Capabilities

| Aspect | API Support | Current Implementation |
|--------|-------------|------------------------|
| Single API key for all databases | ✅ Yes | ✅ Works |
| Page IDs globally unique | ✅ Yes | ✅ Works |
| Database_id in task records | ✅ | ✅ Already stored |
| Property schemas per database | ⚠️ Can differ | ❌ Global config only |

**Key challenge**: Databases may have different property names/types. Needs per-database property configuration.

---

## Target Architecture

```
claudear/
├── pyproject.toml
├── claudear/
│   ├── __init__.py
│   ├── main.py                       # Entry point with auto-detection
│   ├── config.py                     # Unified multi-instance configuration
│   │
│   ├── core/                         # Provider-agnostic core
│   │   ├── types.py                  # TaskId, ProviderInstance, TaskStatus
│   │   ├── state.py                  # TaskStateMachine (unchanged)
│   │   ├── store.py                  # Unified TaskStore (provider + instance_id)
│   │   └── orchestrator.py           # Multi-instance TaskOrchestrator
│   │
│   ├── providers/                    # Provider implementations
│   │   ├── base.py                   # Abstract interfaces
│   │   ├── registry.py               # Provider discovery
│   │   │
│   │   ├── linear/                   # Linear provider
│   │   │   ├── provider.py           # LinearProvider(PMProvider)
│   │   │   ├── client.py             # LinearClient (per-team caching)
│   │   │   ├── models.py             # Pydantic models
│   │   │   ├── labels.py             # Per-team LabelManager pool
│   │   │   └── webhook.py            # WebhookEventSource
│   │   │
│   │   └── notion/                   # Notion provider
│   │       ├── provider.py           # NotionProvider(PMProvider)
│   │       ├── client.py             # Per-database NotionClient pool
│   │       ├── properties.py         # Per-database PropertyManager
│   │       ├── poller.py             # MultiDatabasePoller
│   │       └── webhook.py            # WebhookEventSource (optional)
│   │
│   ├── events/                       # Event abstraction
│   │   ├── types.py                  # Event dataclasses
│   │   └── dispatcher.py             # Event routing
│   │
│   ├── claude/                       # Claude integration (unchanged)
│   │   ├── runner.py
│   │   ├── hooks.py
│   │   └── activity.py
│   │
│   ├── git/                          # Git operations (per-instance)
│   │   ├── worktree.py               # WorktreeManager (one per repo)
│   │   └── github.py                 # GitHubClient (one per repo)
│   │
│   └── server/                       # Optional webhook server
│       ├── app.py
│       └── routes/
│           └── webhooks.py           # Dynamic provider routes
│
└── docs/
    ├── IMPLEMENTATION_PLAN.md
    ├── MULTI_PROVIDER_PLAN.md        # This document
    ├── MIGRATION.md
    └── PROVIDERS.md
```

---

## Key Abstractions

### Task Identification (`core/types.py`)

```python
@dataclass
class TaskId:
    """Unified task identifier across all provider instances."""
    provider: ProviderType           # LINEAR, NOTION, etc.
    instance_id: str                 # Team ID (ENG) or Database ID (abc123)
    external_id: str                 # Linear issue UUID or Notion page UUID
    identifier: str                  # Human-readable: "ENG-123" or "CLO-001"

    @property
    def composite_key(self) -> str:
        """Unique key for storage: 'linear:ENG:uuid' or 'notion:abc123:uuid'."""
        return f"{self.provider.value}:{self.instance_id}:{self.external_id}"
```

### Provider Instance (`core/types.py`)

```python
@dataclass
class ProviderInstance:
    """Configuration for a specific team/database instance."""
    provider: ProviderType
    instance_id: str                 # Team ID or Database ID
    display_name: str                # "Engineering Team" or "Project Alpha"
    repo_path: Path                  # Repository for this team/database

    # Status mappings (optional - provider may auto-detect)
    status_todo: Optional[str] = None
    status_in_progress: Optional[str] = None
    status_in_review: Optional[str] = None
    status_done: Optional[str] = None

    @property
    def worktrees_path(self) -> Path:
        """Default worktrees directory for this instance."""
        return self.repo_path / ".worktrees"
```

### Provider Interface (`providers/base.py`)

```python
class PMProvider(ABC):
    """Abstract base class for project management providers."""

    @abstractmethod
    async def initialize_instance(self, instance: ProviderInstance) -> None:
        """Initialize a specific team/database instance."""
        pass

    @abstractmethod
    async def get_task(self, task_id: TaskId) -> Optional[UnifiedTask]:
        """Fetch a task by ID (routes to correct instance)."""
        pass

    @abstractmethod
    async def update_task_status(self, task_id: TaskId, status: TaskStatus) -> bool:
        """Update task status (routes to correct instance)."""
        pass

    # ... other methods route by task_id.instance_id
```

---

## Configuration

### Unified `.env` Structure

```bash
# =============================================================================
# LINEAR PROVIDER - Multiple Teams (each with its own repo)
# =============================================================================
LINEAR_API_KEY=lin_api_xxxxx
LINEAR_WEBHOOK_SECRET=whsec_xxxxx

# Multiple teams (comma-separated or single value for backward compatibility)
LINEAR_TEAM_IDS=ENG,INFRA,DESIGN
# Or single team (backward compatible):
# LINEAR_TEAM_ID=ENG

# Per-team repository paths (REQUIRED for each team)
LINEAR_ENG_REPO=/path/to/engineering-repo
LINEAR_INFRA_REPO=/path/to/infrastructure-repo
LINEAR_DESIGN_REPO=/path/to/design-system-repo

# Optional: Per-team state mappings (uses state type detection if not set)
# LINEAR_ENG_STATE_TODO=Todo
# LINEAR_INFRA_STATE_TODO=Ready

# Labels (applies to all teams)
LINEAR_LABELS_ENABLED=true
LINEAR_LABELS_ACTIVITY_ENABLED=true

# =============================================================================
# NOTION PROVIDER - Multiple Databases (each with its own repo)
# =============================================================================
NOTION_API_KEY=secret_xxxxx

# Multiple databases (comma-separated or single value)
NOTION_DATABASE_IDS=abc123,def456,ghi789
# Or single database (backward compatible):
# NOTION_DATABASE_ID=abc123

# Per-database repository paths (REQUIRED for each database)
NOTION_abc123_REPO=/path/to/project-alpha-repo
NOTION_def456_REPO=/path/to/project-beta-repo
NOTION_ghi789_REPO=/path/to/project-gamma-repo

# Optional: Per-database status mappings
# NOTION_abc123_STATUS_TODO=Todo
# NOTION_def456_STATUS_TODO=Next

# Event mode and polling
NOTION_EVENT_MODE=polling
NOTION_POLL_INTERVAL=5

# =============================================================================
# SHARED SETTINGS
# =============================================================================
GITHUB_TOKEN=ghp_xxxxx
# Note: REPO_PATH is now per-team/database, not global
# For backward compatibility, REPO_PATH is used if only one team/db is configured
# REPO_PATH=/path/to/repo

MAX_CONCURRENT_TASKS=5
BLOCKED_TIMEOUT=3600

# Server (for webhook providers)
WEBHOOK_PORT=8000
NGROK_AUTHTOKEN=your_token

# Database & Logging
DB_PATH=claudear.db
LOG_LEVEL=INFO
```

### Auto-Detection Logic

```python
@property
def linear_team_ids(self) -> list[str]:
    """Get all configured Linear teams."""
    if self.linear_team_ids_str:
        return [t.strip() for t in self.linear_team_ids_str.split(',')]
    elif self.linear_team_id:  # Backward compatible
        return [self.linear_team_id]
    return []

@property
def notion_database_ids(self) -> list[str]:
    """Get all configured Notion databases."""
    if self.notion_database_ids_str:
        return [d.strip() for d in self.notion_database_ids_str.split(',')]
    elif self.notion_database_id:  # Backward compatible
        return [self.notion_database_id]
    return []
```

---

## Implementation Phases

### Phase 1: Core Abstractions
**Complexity**: Medium | **Effort**: 3-4 days

1. Create `claudear/core/` directory
2. Move `tasks/state.py` to `core/state.py` (unchanged)
3. Create `core/types.py`:
   - `TaskId` with provider + instance_id + external_id
   - `ProviderInstance` for team/database config
   - `TaskStatus` unified enum
4. Generalize `tasks/store.py` to `core/store.py`:
   - Add `provider` column
   - Add `instance_id` column
   - Composite key: `provider:instance_id:external_id`
5. Create `providers/base.py` with abstract interfaces
6. Create `events/types.py` with event dataclasses

### Phase 2: Linear Provider
**Complexity**: Medium | **Effort**: 2-3 days

1. Create `providers/linear/provider.py` implementing `PMProvider`
2. Create `providers/linear/webhook.py` implementing `EventSource`
3. Support `LINEAR_TEAM_IDS` (comma-separated)
4. Per-team LabelManager pool: `dict[str, LabelManager]`
5. Use state `type` field for consistent state detection:
   ```python
   # Instead of matching by name:
   if state_name == settings.linear_state_todo:
   # Use type:
   if state_type == "unstarted":
   ```
6. Register webhooks for ALL teams on startup

### Phase 3: Notion Provider
**Complexity**: Medium | **Effort**: 2-3 days

1. Copy `clotion/notion/` to `claudear/providers/notion/`
2. Create `providers/notion/provider.py` implementing `PMProvider`
3. Support `NOTION_DATABASE_IDS` (comma-separated)
4. Per-database client pool: `dict[str, NotionClient]`
5. MultiDatabasePoller or per-database pollers
6. Per-database PropertyManager
7. Database-aware ID generation: `ABC-CLO-001`, `DEF-CLO-001`

### Phase 4: Unified TaskOrchestrator
**Complexity**: High | **Effort**: 4-5 days

1. Create `core/orchestrator.py`:
   - Manage all provider instances
   - Route events based on `TaskId.provider` + `TaskId.instance_id`
   - Lookup correct client by (provider, instance_id) tuple
2. **Per-instance WorktreeManager** - each team/database has its own repo
   ```python
   self._worktrees: dict[str, WorktreeManager] = {}  # instance_key -> manager
   ```
3. **Per-instance GitHubClient** - PRs created in each repo
   ```python
   self._github_clients: dict[str, GitHubClient] = {}  # instance_key -> client
   ```
4. Shared `ClaudeRunnerPool` across all instances (Claude sessions are repo-agnostic)
5. Unified comment polling for blocked tasks
6. Unified task lifecycle handling

### Phase 5: Unified Entry Point
**Complexity**: Medium | **Effort**: 2-3 days

1. Rewrite `main.py` with auto-detection
2. Parse team/database lists from config
3. Initialize all provider instances
4. Start webhook server if needed
5. Enhanced startup banner showing per-instance repos:
   ```
   ╔════════════════════════════════════════════════════════════════════════╗
   ║                             CLAUDEAR                                    ║
   ║                Multi-Provider Development Automation                    ║
   ╠════════════════════════════════════════════════════════════════════════╣
   ║  LINEAR PROVIDER                                                        ║
   ║    ✓ ENG (Engineering)                                                  ║
   ║        Repo: /Users/dev/engineering-repo                               ║
   ║        Mode: Webhook                                                    ║
   ║    ✓ INFRA (Infrastructure)                                             ║
   ║        Repo: /Users/dev/infrastructure-repo                            ║
   ║        Mode: Webhook                                                    ║
   ║                                                                         ║
   ║  NOTION PROVIDER                                                        ║
   ║    ✓ abc123 (Project Alpha)                                             ║
   ║        Repo: /Users/dev/project-alpha-repo                             ║
   ║        Mode: Polling (5s)                                               ║
   ║    ✓ def456 (Project Beta)                                              ║
   ║        Repo: /Users/dev/project-beta-repo                              ║
   ║        Mode: Polling (5s)                                               ║
   ║                                                                         ║
   ║  Max concurrent tasks: 5                                                ║
   ║  Webhook URL: https://abc.ngrok.io/webhooks/linear                     ║
   ╚════════════════════════════════════════════════════════════════════════╝
   ```

### Phase 6: Migration & Compatibility
**Complexity**: Medium | **Effort**: 2-3 days

1. Database schema migration:
   - Add `provider` column (default: "linear")
   - Add `instance_id` column (default: first configured team)
   - Create composite index
2. Configuration backward compatibility:
   - `LINEAR_TEAM_ID` (singular) still works
   - `NOTION_DATABASE_ID` (singular) still works
3. Migration script: `claudear --migrate`

### Phase 7: Testing & Documentation
**Complexity**: Medium | **Effort**: 3-4 days

1. Unit tests for core, providers, events
2. Integration tests:
   - Single team/database (backward compatible)
   - Multiple teams same provider
   - Multiple databases same provider
   - Multiple providers simultaneously
   - Task isolation between instances
3. Documentation:
   - Update README
   - Create MIGRATION.md
   - Create PROVIDERS.md (adding new providers)

**Total Effort**: 17-24 days

---

## Potential Issues & Mitigations

| Issue | Mitigation |
|-------|------------|
| Task ID collisions | Composite key: `provider:instance_id:external_id` |
| Branch naming conflicts | Prefix: `claudear/linear-ENG-123`, `claudear/notion-abc-CLO-001` |
| State name variation (Linear) | Use state `type` field (`"unstarted"`, `"started"`, etc.) |
| Property heterogeneity (Notion) | Per-database property configuration |
| Polling efficiency | Staggered polling, rate limiting for many databases |
| Config complexity | Good defaults, backward compatible single-instance config |
| Webhook registration | Auto-register for all teams on startup |
| Instance isolation | Route all operations through TaskId with instance_id |
| Multiple repos | Per-instance WorktreeManager and GitHubClient |
| Claude working directory | Run Claude in correct repo via worktree path |
| Git authentication | Single GITHUB_TOKEN works for all repos (if same account) |

---

## Instance Resource Management

Each team/database instance manages its own isolated resources:

### Per-Instance Resources

```python
# In core/orchestrator.py
class TaskOrchestrator:
    def __init__(self, instances: list[ProviderInstance], ...):
        # Per-instance resources keyed by "provider:instance_id"
        self._worktrees: dict[str, WorktreeManager] = {}
        self._github_clients: dict[str, GitHubClient] = {}
        self._label_managers: dict[str, LabelManager] = {}  # Linear only
        self._property_managers: dict[str, PropertyManager] = {}  # Notion only

        # Shared resources
        self._claude_pool = ClaudeRunnerPool(max_concurrent)
        self._store = TaskStore(db_path)

        # Initialize per-instance resources
        for instance in instances:
            key = f"{instance.provider.value}:{instance.instance_id}"
            self._worktrees[key] = WorktreeManager(
                repo_path=instance.repo_path,
                worktrees_dir=instance.worktrees_path,
            )
            self._github_clients[key] = GitHubClient(
                repo_path=instance.repo_path,
            )

    async def start_task(self, task_id: TaskId, ...):
        # Route to correct resources based on instance
        key = f"{task_id.provider.value}:{task_id.instance_id}"
        worktree_mgr = self._worktrees[key]
        github_client = self._github_clients[key]

        # Create worktree in the correct repo
        worktree_path = await worktree_mgr.create(task_id.identifier)

        # Claude runs in the worktree (repo-specific)
        await self._claude_pool.run(
            working_directory=worktree_path,
            prompt=...,
        )
```

### Resource Lifecycle

| Resource | Scope | Created When | Destroyed When |
|----------|-------|--------------|----------------|
| WorktreeManager | Per-instance | Startup | Shutdown |
| GitHubClient | Per-instance | Startup | Shutdown |
| LabelManager | Per-Linear-team | Startup | Shutdown |
| PropertyManager | Per-Notion-DB | Startup | Shutdown |
| ClaudeRunnerPool | Global | Startup | Shutdown |
| TaskStore | Global | Startup | Shutdown |
| Worktree (git) | Per-task | Task starts | Task completes |
| Claude session | Per-task | Task starts | Task completes |

### Example: Task Flow with Multiple Repos

```
1. Webhook received: Issue ENG-123 moved to "Todo"
   ├── task_id = TaskId(LINEAR, "ENG", uuid, "ENG-123")
   └── instance_key = "linear:ENG"

2. Orchestrator routes to ENG resources:
   ├── worktree_mgr = _worktrees["linear:ENG"]  # Uses /path/to/eng-repo
   ├── github = _github_clients["linear:ENG"]    # PRs in eng-repo
   └── labels = _label_managers["linear:ENG"]    # ENG team labels

3. Create worktree:
   └── /path/to/eng-repo/.worktrees/claudear-ENG-123/

4. Run Claude in worktree:
   └── working_directory = /path/to/eng-repo/.worktrees/claudear-ENG-123/

5. Create PR in eng-repo:
   └── gh pr create (in eng-repo)
```

---

## Future Extensibility

Adding a new provider (e.g., Jira) requires:

1. Create `providers/jira/` directory
2. Implement `JiraProvider(PMProvider)`
3. Implement `JiraEventSource` (webhook or polling)
4. Add `JIRA_*` config vars to Settings
5. Support `JIRA_PROJECT_IDS` for multiple projects

Adding a new instance (team/database) requires only `.env` changes:
```bash
# Add a new Linear team with its repo:
LINEAR_TEAM_IDS=ENG,INFRA,DESIGN,SECURITY
LINEAR_SECURITY_REPO=/path/to/security-repo

# Add a new Notion database with its repo:
NOTION_DATABASE_IDS=abc123,def456,ghi789,jkl012
NOTION_jkl012_REPO=/path/to/new-project-repo
```

No code changes needed for new instances - just add the ID to the list and specify its repo.

---

## Migration for Existing Users

### Claudear Users (Linear)

1. Update to new version: `pip install --upgrade claudear`
2. Run migration: `claudear --migrate`
3. No `.env` changes required - single team continues to work
4. Optionally add more teams: `LINEAR_TEAM_IDS=ENG,INFRA`

### Clotion Users (Notion)

1. Install Claudear: `pip install claudear`
2. Update `.env`:
   - Rename `NOTION_DATABASE_ID` (works as-is for backward compat)
   - Add other Claudear settings if needed
3. Run: `claudear`

### New Multi-Instance Users

1. Install: `pip install claudear`
2. Configure `.env` with all teams/databases and their repos:
   ```bash
   # Linear teams
   LINEAR_API_KEY=lin_api_xxxxx
   LINEAR_WEBHOOK_SECRET=whsec_xxxxx
   LINEAR_TEAM_IDS=ENG,INFRA
   LINEAR_ENG_REPO=/path/to/engineering-repo
   LINEAR_INFRA_REPO=/path/to/infrastructure-repo

   # Notion databases
   NOTION_API_KEY=secret_xxxxx
   NOTION_DATABASE_IDS=abc123,def456
   NOTION_abc123_REPO=/path/to/project-alpha-repo
   NOTION_def456_REPO=/path/to/project-beta-repo

   # Shared
   GITHUB_TOKEN=ghp_xxxxx
   ```
3. Run: `claudear`
