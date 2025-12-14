"""Taskiq example with sqladbx and Redis broker.

This example demonstrates:
- Background task processing with Taskiq and Redis
- Database operations in async tasks
- Worker process with proper lifecycle management
- Task scheduling and execution

Requirements:
    redis-server on localhost:6379

Run:
    # Terminal 1: Start worker
    uv run taskiq worker examples.taskiq_basic:broker

    # Terminal 2: Run example tasks
    uv run python examples/taskiq_basic.py
"""

from loguru import logger
from sqlmodel import Field, SQLModel, select
from taskiq import TaskiqEvents, TaskiqState
from taskiq_redis import ListQueueBroker

from sqladbx import db

# ============================================================================
# Models
# ============================================================================


class User(SQLModel, table=True):
    """User model."""

    __tablename__ = "users"

    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(max_length=100)
    email: str = Field(max_length=100, unique=True)
    notifications_sent: int = Field(default=0)


class EmailLog(SQLModel, table=True):
    """Email log model."""

    __tablename__ = "email_logs"

    id: int | None = Field(default=None, primary_key=True)
    recipient: str = Field(max_length=100)
    subject: str = Field(max_length=200)
    status: str = Field(max_length=50)


# ============================================================================
# Taskiq Broker
# ============================================================================

# Redis broker with worker support
broker = ListQueueBroker(url="redis://localhost:6379")


@broker.on_event(TaskiqEvents.WORKER_STARTUP)
async def startup_broker(_: TaskiqState) -> None:
    """Initialize database on worker startup."""
    db.initialize(db_url="sqlite+aiosqlite:///./taskiq_example.db")
    async with db.engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    logger.info("✓ Database initialized")


@broker.on_event(TaskiqEvents.WORKER_SHUTDOWN)
async def shutdown_broker(_: TaskiqState) -> None:
    """Cleanup database on worker shutdown."""
    await db.dispose()
    logger.info("✓ Database cleaned up")


# ============================================================================
# Tasks
# ============================================================================


@broker.task
async def send_email(recipient: str, subject: str) -> dict[str, str]:
    """Send email and log to database.

    Args:
        recipient: Email recipient
        subject: Email subject

    Returns:
        Task result with status
    """
    async with db():
        # Simulate sending email
        logger.info(f"📧 Sending email to {recipient}: {subject}")

        # Log email
        email_log = EmailLog(
            recipient=recipient,
            subject=subject,
            status="sent",
        )
        db.session.add(email_log)
        await db.session.commit()
        await db.session.refresh(email_log)

        return {
            "status": "success",
            "log_id": email_log.id,
            "recipient": recipient,
        }


@broker.task
async def create_user(name: str, email: str) -> dict[str, int | str]:
    """Create a new user.

    Args:
        name: User name
        email: User email

    Returns:
        Created user info
    """
    async with db(commit_on_exit=True):
        user = User(name=name, email=email)
        db.session.add(user)
        await db.session.flush()
        await db.session.refresh(user)

        logger.info(f"✓ Created user: {user.name} ({user.email})")

        return {
            "user_id": user.id,
            "name": user.name,
            "email": user.email,
        }


@broker.task
async def process_users() -> dict[str, int]:
    """Process all users and send notifications.

    Returns:
        Processing statistics
    """
    async with db():
        # Get all users
        result = await db.session.scalars(select(User))
        users = result.all()

        processed = 0
        for user in users:
            # Simulate processing
            logger.info(f"📊 Processing user: {user.name}")

            # Update notification counter
            user.notifications_sent += 1
            processed += 1

        await db.session.commit()

        logger.info(f"✓ Processed {processed} users")

        return {
            "total_users": len(users),
            "processed": processed,
        }


@broker.task
async def cleanup_old_logs() -> dict[str, int]:
    """Cleanup old email logs.

    Returns:
        Cleanup statistics
    """
    async with db():
        # For simplicity, delete all logs (in real app, would filter by date)
        result = await db.session.scalars(select(EmailLog))
        logs = result.all()

        deleted = 0
        for log in logs:
            await db.session.delete(log)
            deleted += 1

        await db.session.commit()

        logger.info(f"🗑️  Deleted {deleted} old email logs")

        return {"deleted": deleted}


@broker.task
async def batch_create_users(users_data: list[dict[str, str]]) -> dict[str, int]:
    """Batch create multiple users.

    Args:
        users_data: List of user data dicts

    Returns:
        Creation statistics
    """
    async with db(commit_on_exit=True):
        users = [User(**data) for data in users_data]
        db.session.add_all(users)
        await db.session.flush()

        logger.info(f"✓ Batch created {len(users)} users")

        return {"created": len(users)}


@broker.task
async def send_notifications_to_all() -> dict[str, int]:
    """Send notifications to all users.

    Returns:
        Notification statistics
    """
    # Get users
    async with db():
        result = await db.session.scalars(select(User))
        users = result.all()
        user_emails = [(u.id, u.email, u.name) for u in users]

    # Send emails (each creates its own db context)
    sent = 0
    for _user_id, email, name in user_emails:
        await send_email.kiq(email, f"Hello {name}!")
        sent += 1

    # Update user notification counters
    async with db():
        for user_id, _, _ in user_emails:
            result = await db.session.scalars(select(User).where(User.id == user_id))
            user = result.one()
            user.notifications_sent += 1

        await db.session.commit()

    logger.info(f"📧 Sent {sent} notifications")

    return {"sent": sent}


# ============================================================================
# Example Usage
# ============================================================================


async def example_usage() -> None:
    """Example of sending tasks to Redis queue."""
    logger.info("\n🚀 Sending tasks to Taskiq worker...\n")
    logger.info("Make sure Redis is running and worker is started:")
    logger.info("  uv run taskiq worker examples.taskiq_basic:broker\n")

    # Create users
    logger.info("1️⃣ Creating users...")
    task1 = await create_user.kiq("Alice", "alice@example.com")
    task2 = await create_user.kiq("Bob", "bob@example.com")
    logger.info(f"  Sent tasks: {task1.task_id}, {task2.task_id}")

    # Batch create
    logger.info("\n2️⃣ Batch creating users...")
    task3 = await batch_create_users.kiq(
        [
            {"name": "Charlie", "email": "charlie@example.com"},
            {"name": "Diana", "email": "diana@example.com"},
        ],
    )
    logger.info(f"  Sent task: {task3.task_id}")

    # Send individual email
    logger.info("\n3️⃣ Sending email...")
    task4 = await send_email.kiq("alice@example.com", "Welcome!")
    logger.info(f"  Sent task: {task4.task_id}")

    # Process all users
    logger.info("\n4️⃣ Processing users...")
    task5 = await process_users.kiq()
    logger.info(f"  Sent task: {task5.task_id}")

    # Send notifications to all
    logger.info("\n5️⃣ Sending notifications...")
    task6 = await send_notifications_to_all.kiq()
    logger.info(f"  Sent task: {task6.task_id}")

    # Cleanup
    logger.info("\n6️⃣ Cleaning up logs...")
    task7 = await cleanup_old_logs.kiq()
    logger.info(f"  Sent task: {task7.task_id}")

    logger.info("\n✅ All tasks sent to queue!")
    logger.info("Check worker terminal for execution logs.\n")


if __name__ == "__main__":
    import asyncio

    asyncio.run(example_usage())
