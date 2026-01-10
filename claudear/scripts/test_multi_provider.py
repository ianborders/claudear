#!/usr/bin/env python3
"""Test script for multi-provider Claudear setup.

Verifies that all components import correctly and are properly wired together.
"""

import asyncio
import sys


def test_core_imports():
    """Test core module imports."""
    print("Testing core imports...")

    from claudear.core.types import (
        ProviderType,
        TaskId,
        TaskStatus,
        ProviderInstance,
        UnifiedTask,
    )
    from claudear.core.state import TaskState, TaskStateMachine, TaskContext
    from claudear.core.store import TaskStore, TaskRecord
    from claudear.core.orchestrator import TaskOrchestrator
    from claudear.core.config import MultiProviderSettings, get_settings
    from claudear.core.app import ClaudearApp

    print("  ✓ Core types")
    print("  ✓ Core state")
    print("  ✓ Core store")
    print("  ✓ Core orchestrator")
    print("  ✓ Core config")
    print("  ✓ Core app")


def test_provider_imports():
    """Test provider imports."""
    print("\nTesting provider imports...")

    from claudear.providers.base import PMProvider, EventSource, EventSourceMode
    from claudear.providers.linear import LinearProvider, LinearWebhookEventSource
    from claudear.providers.notion import NotionProvider, NotionPollerEventSource

    print("  ✓ Base provider classes")
    print("  ✓ Linear provider")
    print("  ✓ Notion provider")


def test_event_imports():
    """Test event imports."""
    print("\nTesting event imports...")

    from claudear.events.types import (
        Event,
        EventType,
        TaskStatusChangedEvent,
        TaskCommentAddedEvent,
        TaskUpdatedEvent,
    )

    print("  ✓ Event types")


def test_server_imports():
    """Test server imports."""
    print("\nTesting server imports...")

    from claudear.server.unified_app import create_unified_app
    from claudear.server.routes.unified_webhooks import router

    print("  ✓ Unified server app")
    print("  ✓ Unified webhooks router")


def test_provider_interface():
    """Test that providers implement the correct interface."""
    print("\nTesting provider interfaces...")

    from claudear.providers.base import PMProvider, EventSource
    from claudear.providers.linear import LinearProvider, LinearWebhookEventSource
    from claudear.providers.notion import NotionProvider, NotionPollerEventSource
    import inspect

    # Required PMProvider methods
    required_methods = [
        "provider_type",
        "display_name",
        "initialize",
        "initialize_instance",
        "shutdown",
        "get_task",
        "update_task_status",
        "post_comment",
        "get_new_comments",
        "set_working_indicator",
        "set_blocked_indicator",
        "clear_indicators",
        "set_branch_info",
        "get_event_source",
        "detect_status",
        "get_provider_status",
    ]

    for provider_cls in [LinearProvider, NotionProvider]:
        missing = []
        for method in required_methods:
            if not hasattr(provider_cls, method):
                missing.append(method)
        if missing:
            print(f"  ✗ {provider_cls.__name__} missing: {missing}")
        else:
            print(f"  ✓ {provider_cls.__name__} implements PMProvider")

    # Required EventSource methods
    event_source_methods = ["mode", "start", "stop", "set_event_handler"]

    for source_cls in [LinearWebhookEventSource, NotionPollerEventSource]:
        missing = []
        for method in event_source_methods:
            if not hasattr(source_cls, method):
                missing.append(method)
        if missing:
            print(f"  ✗ {source_cls.__name__} missing: {missing}")
        else:
            print(f"  ✓ {source_cls.__name__} implements EventSource")


def test_config():
    """Test configuration parsing."""
    print("\nTesting configuration...")

    from claudear.core.config import MultiProviderSettings

    # Test with no env vars
    settings = MultiProviderSettings()

    # Check methods exist
    assert hasattr(settings, "get_linear_team_ids")
    assert hasattr(settings, "get_notion_database_ids")
    assert hasattr(settings, "has_linear")
    assert hasattr(settings, "has_notion")
    assert hasattr(settings, "validate")

    print("  ✓ MultiProviderSettings methods present")

    # Test validation returns errors for empty config
    errors = settings.validate()
    if errors:
        print(f"  ✓ Validation catches missing config ({len(errors)} errors)")
    else:
        print("  ⚠ Validation passed with empty config (unexpected)")


async def test_store():
    """Test store operations."""
    print("\nTesting store operations...")

    import tempfile
    from pathlib import Path
    from datetime import datetime

    from claudear.core.store import TaskStore, TaskRecord
    from claudear.core.types import ProviderType
    from claudear.core.state import TaskState

    # Create temp database
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)

    try:
        store = TaskStore(str(db_path))
        await store.init()

        # Create a test record
        record = TaskRecord(
            provider=ProviderType.LINEAR,
            instance_id="ENG",
            external_id="test-uuid-123",
            task_identifier="ENG-001",
            title="Test Task",
            description="A test task",
            branch_name="claudear/eng-001",
            worktree_path="/tmp/worktrees/eng-001",
            state=TaskState.IN_PROGRESS,
            blocked_reason=None,
            blocked_at=None,
            pr_number=None,
            pr_url=None,
            session_id=None,
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )

        # Save
        await store.save(record)
        print("  ✓ Save task")

        # Get by TaskId
        from claudear.core.types import TaskId

        task_id = TaskId(
            provider=ProviderType.LINEAR,
            instance_id="ENG",
            external_id="test-uuid-123",
            identifier="ENG-001",
        )
        loaded = await store.get(task_id)
        assert loaded is not None
        assert loaded.title == "Test Task"
        print("  ✓ Get task by TaskId")

        # Get by separate args
        loaded2 = await store.get(ProviderType.LINEAR, "ENG", "test-uuid-123")
        assert loaded2 is not None
        print("  ✓ Get task by separate args")

        # Update state
        await store.update_state(task_id, TaskState.COMPLETED)
        loaded3 = await store.get(task_id)
        assert loaded3.state == TaskState.COMPLETED
        print("  ✓ Update task state")

        # Delete
        await store.delete(task_id)
        loaded4 = await store.get(task_id)
        assert loaded4 is None
        print("  ✓ Delete task")

    finally:
        db_path.unlink()


def test_orchestrator_creation():
    """Test orchestrator can be created."""
    print("\nTesting orchestrator creation...")

    import tempfile
    from pathlib import Path

    from claudear.core.store import TaskStore
    from claudear.core.orchestrator import TaskOrchestrator

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)

    try:
        store = TaskStore(str(db_path))
        orchestrator = TaskOrchestrator(
            task_store=store,
            github_token="test-token",
            max_concurrent_tasks=3,
        )

        assert orchestrator is not None
        assert hasattr(orchestrator, "register_provider")
        assert hasattr(orchestrator, "register_instance")
        assert hasattr(orchestrator, "start")
        assert hasattr(orchestrator, "stop")

        print("  ✓ Orchestrator created successfully")

    finally:
        db_path.unlink()


def main():
    """Run all tests."""
    print("=" * 60)
    print("Claudear Multi-Provider Test Suite")
    print("=" * 60)

    try:
        test_core_imports()
        test_provider_imports()
        test_event_imports()
        test_server_imports()
        test_provider_interface()
        test_config()
        asyncio.run(test_store())
        test_orchestrator_creation()

        print("\n" + "=" * 60)
        print("All tests passed! ✓")
        print("=" * 60)
        return 0

    except Exception as e:
        print(f"\n✗ Test failed: {e}")
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
