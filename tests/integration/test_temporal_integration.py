"""Integration tests for Temporal workflows and activities."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel import Field, SQLModel

from sqladbx import DBProxy, db

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator


class Task(SQLModel, table=True):
    """Task model for testing."""

    id: int | None = Field(default=None, primary_key=True)
    title: str
    status: str = "pending"
    workflow_id: str | None = None


@pytest.fixture
async def temporal_db() -> AsyncGenerator[DBProxy]:
    """Create a test database for Temporal tests."""
    db_path = Path("test_temporal.db")
    if db_path.exists():
        db_path.unlink()

    engine = create_async_engine(
        f"sqlite+aiosqlite:///{db_path}",
        echo=False,
    )

    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    db.initialize(engine)

    yield db

    await engine.dispose()
    if db_path.exists():
        db_path.unlink()


@pytest.mark.asyncio
async def test_temporal_workflow_with_db_context(temporal_db: DBProxy) -> None:
    """Test that db is accessible within Temporal workflow context."""
    # Simulate Temporal workflow execution
    async with temporal_db():
        # Create task in workflow
        task = Task(title="Process user data", workflow_id="wf-123")
        temporal_db.session.add(task)
        await temporal_db.session.commit()
        await temporal_db.session.refresh(task)

        assert task.id is not None
        assert task.title == "Process user data"
        assert task.workflow_id == "wf-123"


@pytest.mark.asyncio
async def test_temporal_activity_with_db_context(temporal_db: DBProxy) -> None:
    """Test that db is accessible within Temporal activity."""
    # Simulate activity execution
    async with temporal_db():
        # Activity: Create task
        task = Task(title="Send email notification", status="pending")
        temporal_db.session.add(task)
        await temporal_db.session.commit()
        await temporal_db.session.refresh(task)

        task_id = task.id

    # Simulate another activity: Update task
    async with temporal_db():
        result = await temporal_db.session.execute(
            sa.select(Task).where(Task.id == task_id),
        )
        task = result.scalar_one()
        task.status = "completed"
        await temporal_db.session.commit()

    # Verify final state
    async with temporal_db():
        result = await temporal_db.session.execute(
            sa.select(Task).where(Task.id == task_id),
        )
        final_task = result.scalar_one()
        assert final_task.status == "completed"


@pytest.mark.asyncio
async def test_temporal_workflow_with_multiple_activities(temporal_db: DBProxy) -> None:
    """Test workflow with multiple activities accessing db."""
    workflow_id = "wf-multi-456"

    # Activity 1: Initialize task
    async with temporal_db():
        task = Task(title="Complex workflow", workflow_id=workflow_id, status="started")
        temporal_db.session.add(task)
        await temporal_db.session.commit()
        await temporal_db.session.refresh(task)
        task_id = task.id

    # Activity 2: Process task
    async with temporal_db():
        result = await temporal_db.session.execute(
            sa.select(Task).where(Task.id == task_id),
        )
        task = result.scalar_one()
        task.status = "processing"
        await temporal_db.session.commit()

    # Activity 3: Complete task
    async with temporal_db():
        result = await temporal_db.session.execute(
            sa.select(Task).where(Task.id == task_id),
        )
        task = result.scalar_one()
        task.status = "completed"
        await temporal_db.session.commit()

    # Verify workflow result
    async with temporal_db():
        result = await temporal_db.session.execute(
            sa.select(Task).where(Task.workflow_id == workflow_id),
        )
        tasks = result.scalars().all()
        assert len(tasks) == 1
        assert tasks[0].status == "completed"


@pytest.mark.asyncio
async def test_temporal_workflow_with_rollback(temporal_db: DBProxy) -> None:
    """Test that db rollback works correctly in workflow context."""
    async with temporal_db():
        task = Task(title="Failed task", status="started")
        temporal_db.session.add(task)
        await temporal_db.session.commit()
        await temporal_db.session.refresh(task)
        task_id = task.id

    # Simulate activity failure with rollback
    try:
        async with temporal_db():
            result = await temporal_db.session.execute(
                sa.select(Task).where(Task.id == task_id),
            )
            task = result.scalar_one()
            task.status = "processing"
            await temporal_db.session.flush()

            # Simulate error
            raise RuntimeError("Activity failed")  # noqa: EM101, TRY003, TRY301
    except RuntimeError:
        pass

    # Verify rollback - status should still be "started"
    async with temporal_db():
        result = await temporal_db.session.execute(
            sa.select(Task).where(Task.id == task_id),
        )
        task = result.scalar_one()
        assert task.status == "started"


@pytest.mark.asyncio
async def test_temporal_workflow_with_auto_commit(temporal_db: DBProxy) -> None:
    """Test workflow with auto-commit enabled."""
    async with temporal_db(commit_on_exit=True):
        task = Task(title="Auto-commit task", status="completed")
        temporal_db.session.add(task)
        # No manual commit needed

    # Verify task was committed
    async with temporal_db():
        result = await temporal_db.session.execute(sa.select(Task))
        tasks = result.scalars().all()
        assert len(tasks) == 1
        assert tasks[0].title == "Auto-commit task"


@pytest.mark.asyncio
async def test_temporal_workflow_isolation(temporal_db: DBProxy) -> None:
    """Test that workflow contexts are isolated."""
    # Workflow 1
    async with temporal_db():
        task1 = Task(title="Workflow 1 task", workflow_id="wf-1")
        temporal_db.session.add(task1)
        await temporal_db.session.commit()

    # Workflow 2 - should not see uncommitted changes from workflow 1 session
    async with temporal_db():
        task2 = Task(title="Workflow 2 task", workflow_id="wf-2")
        temporal_db.session.add(task2)
        await temporal_db.session.commit()

    # Verify both workflows created tasks independently
    async with temporal_db():
        result = await temporal_db.session.execute(sa.select(Task))
        tasks = result.scalars().all()
        extected_task_count = 2
        assert len(tasks) == extected_task_count
        workflow_ids = {t.workflow_id for t in tasks}
        assert workflow_ids == {"wf-1", "wf-2"}


@pytest.mark.asyncio
async def test_temporal_with_mocked_workflow(temporal_db: DBProxy) -> None:
    """Test Temporal integration with mocked workflow info."""
    # Create mock workflow info
    mock_workflow_info = MagicMock()
    mock_workflow_info.workflow_id = "mock-wf-789"

    # Simulate workflow execution with db access
    async with temporal_db():
        task = Task(
            title="Mocked workflow task",
            workflow_id=mock_workflow_info.workflow_id,
            status="running",
        )
        temporal_db.session.add(task)
        await temporal_db.session.commit()
        await temporal_db.session.refresh(task)

        assert task.workflow_id == "mock-wf-789"


@pytest.mark.asyncio
async def test_temporal_activity_with_query(temporal_db: DBProxy) -> None:
    """Test complex query in Temporal activity context."""
    # Setup: Create multiple tasks
    async with temporal_db():
        tasks = [Task(title=f"Task {i}", status="pending", workflow_id="wf-query") for i in range(5)]
        temporal_db.session.add_all(tasks)
        await temporal_db.session.commit()

    # Activity: Query and update tasks
    async with temporal_db():
        result = await temporal_db.session.execute(
            sa.select(Task).where(Task.workflow_id == "wf-query"),
        )
        tasks = result.scalars().all()

        for task in tasks:
            task.status = "processed"

        await temporal_db.session.commit()

    # Verify all tasks were updated
    async with temporal_db():
        result = await temporal_db.session.execute(
            sa.select(Task).where(
                Task.workflow_id == "wf-query",
                Task.status == "processed",
            ),
        )
        processed_tasks = result.scalars().all()
        exptected_processed_count = 5
        assert len(processed_tasks) == exptected_processed_count
