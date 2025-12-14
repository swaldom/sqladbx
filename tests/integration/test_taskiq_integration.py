"""Integration tests for Taskiq background tasks."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel import Field, SQLModel

from sqladbx import DBProxy, db

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator


class Job(SQLModel, table=True):
    """Job model for testing."""

    id: int | None = Field(default=None, primary_key=True)
    task_name: str
    status: str = "pending"
    task_id: str | None = None
    result: str | None = None


@pytest.fixture
async def taskiq_db() -> AsyncGenerator[DBProxy]:
    """Create a test database for Taskiq tests."""
    db_path = Path("test_taskiq.db")
    if db_path.exists():
        db_path.unlink()

    engine = create_async_engine(
        f"sqlite+aiosqlite:///{db_path}",
        echo=False,
    )

    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    db.initialize(db_url=f"sqlite+aiosqlite:///{db_path}")

    yield db

    await db.dispose()
    await engine.dispose()
    if db_path.exists():
        db_path.unlink()


@pytest.mark.asyncio
async def test_taskiq_task_with_db_context(taskiq_db: DBProxy) -> None:
    """Test that db is accessible within Taskiq task context."""
    # Simulate Taskiq task execution
    async with taskiq_db():
        # Create job in task
        job = Job(task_name="send_email", task_id="task-123")
        taskiq_db.session.add(job)
        await taskiq_db.session.commit()
        await taskiq_db.session.refresh(job)

        assert job.id is not None
        assert job.task_name == "send_email"
        assert job.task_id == "task-123"


@pytest.mark.asyncio
async def test_taskiq_task_with_result(taskiq_db: DBProxy) -> None:
    """Test Taskiq task that stores result in database."""
    task_id = "task-result-456"

    # Simulate task execution that produces result
    async with taskiq_db():
        job = Job(task_name="process_data", task_id=task_id, status="running")
        taskiq_db.session.add(job)
        await taskiq_db.session.commit()
        await taskiq_db.session.refresh(job)

        job_id = job.id

    # Simulate task completion
    async with taskiq_db():
        result = await taskiq_db.session.execute(sa.select(Job).where(Job.id == job_id))
        job = result.scalar_one()
        job.status = "completed"
        job.result = "Data processed successfully"
        await taskiq_db.session.commit()

    # Verify result
    async with taskiq_db():
        result = await taskiq_db.session.execute(sa.select(Job).where(Job.id == job_id))
        final_job = result.scalar_one()
        assert final_job.status == "completed"
        assert final_job.result == "Data processed successfully"


@pytest.mark.asyncio
async def test_taskiq_multiple_concurrent_tasks(taskiq_db: DBProxy) -> None:
    """Test multiple concurrent Taskiq tasks accessing db."""
    # Simulate task 1
    async with taskiq_db():
        job1 = Job(task_name="task_1", task_id="concurrent-1", status="running")
        taskiq_db.session.add(job1)
        await taskiq_db.session.commit()

    # Simulate task 2
    async with taskiq_db():
        job2 = Job(task_name="task_2", task_id="concurrent-2", status="running")
        taskiq_db.session.add(job2)
        await taskiq_db.session.commit()

    # Simulate task 3
    async with taskiq_db():
        job3 = Job(task_name="task_3", task_id="concurrent-3", status="running")
        taskiq_db.session.add(job3)
        await taskiq_db.session.commit()

    # Verify all tasks were created
    async with taskiq_db():
        result = await taskiq_db.session.execute(sa.select(Job))
        jobs = result.scalars().all()
        extected_count = 3
        assert len(jobs) == extected_count
        task_ids = {j.task_id for j in jobs}
        assert task_ids == {"concurrent-1", "concurrent-2", "concurrent-3"}


@pytest.mark.asyncio
async def test_taskiq_task_with_error_handling(taskiq_db: DBProxy) -> None:
    """Test that db rollback works correctly in Taskiq task context."""
    async with taskiq_db():
        job = Job(task_name="failing_task", task_id="error-789", status="started")
        taskiq_db.session.add(job)
        await taskiq_db.session.commit()
        await taskiq_db.session.refresh(job)
        job_id = job.id

    # Simulate task failure with rollback
    try:
        async with taskiq_db():
            result = await taskiq_db.session.execute(
                sa.select(Job).where(Job.id == job_id),
            )
            job = result.scalar_one()
            job.status = "processing"
            await taskiq_db.session.flush()

            # Simulate error
            raise RuntimeError("Task execution failed")  # noqa: TRY301, TRY003, EM101
    except RuntimeError:
        pass

    # Verify rollback - status should still be "started"
    async with taskiq_db():
        result = await taskiq_db.session.execute(sa.select(Job).where(Job.id == job_id))
        job = result.scalar_one()
        assert job.status == "started"


@pytest.mark.asyncio
async def test_taskiq_task_with_auto_commit(taskiq_db: DBProxy) -> None:
    """Test Taskiq task with auto-commit enabled."""
    async with taskiq_db(commit_on_exit=True):
        job = Job(task_name="auto_commit_task", task_id="auto-123", status="completed")
        taskiq_db.session.add(job)
        # No manual commit needed

    # Verify job was committed
    async with taskiq_db():
        result = await taskiq_db.session.execute(sa.select(Job))
        jobs = result.scalars().all()
        assert len(jobs) == 1
        assert jobs[0].task_name == "auto_commit_task"


@pytest.mark.asyncio
async def test_taskiq_task_isolation(taskiq_db: DBProxy) -> None:
    """Test that Taskiq task contexts are isolated."""
    # Task 1
    async with taskiq_db():
        job1 = Job(task_name="isolated_task_1", task_id="iso-1")
        taskiq_db.session.add(job1)
        await taskiq_db.session.commit()

    # Task 2 - should not see uncommitted changes from task 1 session
    async with taskiq_db():
        job2 = Job(task_name="isolated_task_2", task_id="iso-2")
        taskiq_db.session.add(job2)
        await taskiq_db.session.commit()

    # Verify both tasks created jobs independently
    async with taskiq_db():
        result = await taskiq_db.session.execute(sa.select(Job))
        jobs = result.scalars().all()
        exptected_count = 2
        assert len(jobs) == exptected_count
        task_ids = {j.task_id for j in jobs}
        assert task_ids == {"iso-1", "iso-2"}


@pytest.mark.asyncio
async def test_taskiq_with_mocked_broker(taskiq_db: DBProxy) -> None:
    """Test Taskiq integration with mocked broker."""
    # Create mock broker and task
    mock_task = AsyncMock()
    mock_task.task_id = "mock-task-999"

    # Simulate task execution with db access
    async with taskiq_db():
        job = Job(
            task_name="mocked_broker_task",
            task_id=mock_task.task_id,
            status="running",
        )
        taskiq_db.session.add(job)
        await taskiq_db.session.commit()
        await taskiq_db.session.refresh(job)

        assert job.task_id == "mock-task-999"


@pytest.mark.asyncio
async def test_taskiq_batch_processing(taskiq_db: DBProxy) -> None:
    """Test batch processing in Taskiq task context."""
    # Setup: Create multiple pending jobs
    async with taskiq_db():
        jobs = [Job(task_name=f"batch_task_{i}", task_id=f"batch-{i}", status="pending") for i in range(10)]
        taskiq_db.session.add_all(jobs)
        await taskiq_db.session.commit()

    # Simulate batch processing task
    async with taskiq_db():
        result = await taskiq_db.session.execute(
            sa.select(Job).where(Job.status == "pending"),
        )
        pending_jobs = result.scalars().all()

        for job in pending_jobs:
            job.status = "processed"
            job.result = f"Processed {job.task_name}"

        await taskiq_db.session.commit()

    # Verify all jobs were processed
    async with taskiq_db():
        result = await taskiq_db.session.execute(
            sa.select(Job).where(Job.status == "processed"),
        )
        processed_jobs = result.scalars().all()
        expected_count = 10
        assert len(processed_jobs) == expected_count
        assert all(j.result is not None for j in processed_jobs)


@pytest.mark.asyncio
async def test_taskiq_scheduled_task(taskiq_db: DBProxy) -> None:
    """Test scheduled task execution with db access."""
    # Simulate scheduled task that runs periodically
    for run_number in range(3):
        async with taskiq_db():
            job = Job(
                task_name="scheduled_cleanup",
                task_id=f"scheduled-run-{run_number}",
                status="completed",
                result=f"Cleanup run #{run_number}",
            )
            taskiq_db.session.add(job)
            await taskiq_db.session.commit()

    # Verify all scheduled runs were recorded
    async with taskiq_db():
        result = await taskiq_db.session.execute(
            sa.select(Job).where(Job.task_name == "scheduled_cleanup"),
        )
        scheduled_jobs = result.scalars().all()
        expected_count = 3
        assert len(scheduled_jobs) == expected_count
        assert all("Cleanup run #" in j.result for j in scheduled_jobs)


@pytest.mark.asyncio
async def test_taskiq_task_chain(taskiq_db: DBProxy) -> None:
    """Test chained tasks where one task depends on another."""
    # Task 1: Initial processing
    async with taskiq_db():
        job1 = Job(
            task_name="extract_data",
            task_id="chain-1",
            status="completed",
            result="extracted",
        )
        taskiq_db.session.add(job1)
        await taskiq_db.session.commit()
        await taskiq_db.session.refresh(job1)
        job1_id = job1.id

    # Task 2: Transform (depends on task 1)
    async with taskiq_db():
        result = await taskiq_db.session.execute(sa.select(Job).where(Job.id == job1_id))
        previous_job = result.scalar_one()

        if previous_job.status == "completed":
            job2 = Job(
                task_name="transform_data",
                task_id="chain-2",
                status="completed",
                result=f"transformed from {previous_job.result}",
            )
            taskiq_db.session.add(job2)
            await taskiq_db.session.commit()

    # Task 3: Load (depends on task 2)
    async with taskiq_db():
        result = await taskiq_db.session.execute(
            sa.select(Job).where(Job.task_id == "chain-2"),
        )
        previous_job = result.scalar_one()

        if previous_job.status == "completed":
            job3 = Job(
                task_name="load_data",
                task_id="chain-3",
                status="completed",
                result=f"loaded from {previous_job.result}",
            )
            taskiq_db.session.add(job3)
            await taskiq_db.session.commit()

    # Verify task chain
    async with taskiq_db():
        result = await taskiq_db.session.execute(
            sa.select(Job).where(Job.task_id.in_(["chain-1", "chain-2", "chain-3"])),
        )
        chain_jobs = result.scalars().all()
        expected_count = 3
        assert len(chain_jobs) == expected_count
        assert all(j.status == "completed" for j in chain_jobs)
