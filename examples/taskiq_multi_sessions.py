"""Taskiq example with multi-session concurrent operations.

This example demonstrates:
- Multiple concurrent sessions in a single task
- Parallel database operations with transaction isolation
- Handling multiple connections simultaneously
- Use cases: batch processing, complex transactions

Requirements:
    redis-server on localhost:6379

Run:
    # Terminal 1: Start worker
    uv run taskiq worker examples.taskiq_multi_sessions:broker

    # Terminal 2: Run example tasks
    uv run python examples/taskiq_multi_sessions.py
"""

import asyncio

from loguru import logger
from sqlalchemy import text
from sqlmodel import Field, SQLModel, select
from taskiq import TaskiqEvents, TaskiqState
from taskiq_redis import ListQueueBroker

from sqladbx import db

# ============================================================================
# Models
# ============================================================================


class Account(SQLModel, table=True):
    """Bank account model."""

    __tablename__ = "accounts"

    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(max_length=100)
    balance: float = Field(default=0.0)


class Transaction(SQLModel, table=True):
    """Transaction log model."""

    __tablename__ = "transactions"

    id: int | None = Field(default=None, primary_key=True)
    from_account_id: int
    to_account_id: int
    amount: float
    status: str = Field(max_length=50)


# ============================================================================
# Taskiq Broker
# ============================================================================

broker = ListQueueBroker(url="redis://localhost:6379")


@broker.on_event(TaskiqEvents.WORKER_STARTUP)
async def startup_broker(_: TaskiqState) -> None:
    """Initialize database on worker startup."""
    db.initialize(db_url="sqlite+aiosqlite:///./taskiq_multi.db?timeout=30")
    async with db.engine.begin() as conn:
        await conn.execute(text("PRAGMA journal_mode=WAL"))
        await conn.run_sync(SQLModel.metadata.create_all)
    logger.info("✓ Database initialized with WAL mode")


@broker.on_event(TaskiqEvents.WORKER_SHUTDOWN)
async def shutdown_broker(_: TaskiqState) -> None:
    """Cleanup database on worker shutdown."""
    await db.dispose()
    logger.info("✓ Database cleaned up")


# ============================================================================
# Tasks with Multi-Session Support
# ============================================================================


@broker.task
async def create_accounts(accounts: list[dict[str, str | float]]) -> dict[str, int]:
    """Create multiple accounts using separate sessions for isolation.

    Args:
        accounts: List of account data

    Returns:
        Creation statistics
    """
    async with db(multi_sessions=True):
        created = 0

        # Each iteration gets a NEW session via db.session
        for account_data in accounts:
            session = db.session  # New session
            account = Account(**account_data)
            session.add(account)
            await session.commit()
            created += 1
            logger.info(f"✓ Created account: {account.name} in session {id(session)}")

        logger.info(f"✓ Created {created} accounts using multiple sessions")
        return {"created": created}


@broker.task
async def transfer_money_concurrent(
    from_id: int,
    to_id: int,
    amount: float,
) -> dict[str, str]:
    """Transfer money using separate sessions for read and write operations.

    Demonstrates:
    - Session 1: Read accounts
    - Session 2: Update balances
    - Session 3: Log transaction

    Args:
        from_id: Source account ID
        to_id: Destination account ID
        amount: Amount to transfer

    Returns:
        Transfer result
    """
    async with db(multi_sessions=True):
        # Session 1: Read source account
        session1 = db.session
        result = await session1.execute(select(Account).where(Account.id == from_id))
        from_account = result.scalar_one_or_none()
        logger.info(f"📖 Read from_account in session {id(session1)}")

        # Session 2: Read destination account
        session2 = db.session  # Different session!
        result = await session2.execute(select(Account).where(Account.id == to_id))
        to_account = result.scalar_one_or_none()
        logger.info(f"📖 Read to_account in session {id(session2)}")

        if not from_account or not to_account:
            return {"status": "error", "message": "Account not found"}

        if from_account.balance < amount:
            return {"status": "error", "message": "Insufficient funds"}

        # Session 3: Update source account
        session3 = db.session  # Another new session!
        result = await session3.execute(select(Account).where(Account.id == from_id))
        from_account_update = result.scalar_one()
        from_account_update.balance -= amount
        await session3.commit()
        logger.info(f"💰 Updated from_account in session {id(session3)}")

        # Session 4: Update destination account
        session4 = db.session  # Yet another session!
        result = await session4.execute(select(Account).where(Account.id == to_id))
        to_account_update = result.scalar_one()
        to_account_update.balance += amount
        await session4.commit()
        logger.info(f"💰 Updated to_account in session {id(session4)}")

        # Session 5: Log transaction
        session5 = db.session
        transaction = Transaction(
            from_account_id=from_id,
            to_account_id=to_id,
            amount=amount,
            status="completed",
        )
        session5.add(transaction)
        await session5.commit()
        logger.info(f"📝 Logged transaction in session {id(session5)}")

        logger.info(
            f"✅ Transfer completed: ${amount} from {from_account.name} to {to_account.name}",
        )
        logger.info(
            f"   Used 5 different sessions: {id(session1)}, {id(session2)}, "
            f"{id(session3)}, {id(session4)}, {id(session5)}",
        )

        return {
            "status": "success",
            "from": from_account.name,
            "to": to_account.name,
            "amount": amount,
        }


@broker.task
async def batch_update_balances(updates: list[dict[str, int | float]]) -> dict[str, int]:
    """Update multiple account balances using separate sessions.

    Each update happens in its own isolated session.

    Args:
        updates: List of {account_id, amount} dicts

    Returns:
        Update statistics
    """
    async with db(multi_sessions=True):
        updated = 0

        for update in updates:
            # Each update gets its own session
            session = db.session
            account_id = update["account_id"]
            amount = update["amount"]

            result = await session.execute(
                select(Account).where(Account.id == account_id),
            )
            account = result.scalar_one_or_none()

            if account:
                account.balance += amount
                await session.commit()
                updated += 1
                logger.info(
                    f"💵 Updated {account.name}: +${amount} (session {id(session)})",
                )

        logger.info(f"✓ Updated {updated} accounts with separate sessions")
        return {"updated": updated}


@broker.task
async def get_account_summary() -> dict[str, list[dict[str, str | float]]]:
    """Get account summary using multiple sessions for parallel reads.

    Demonstrates concurrent read operations.

    Returns:
        Account summaries
    """
    async with db(multi_sessions=True):
        # Session 1: Get all accounts
        session1 = db.session
        accounts_result = await session1.execute(select(Account))
        accounts = accounts_result.scalars().all()
        logger.info(f"📊 Read {len(accounts)} accounts in session {id(session1)}")

        # Session 2: Get all transactions
        session2 = db.session
        transactions_result = await session2.execute(select(Transaction))
        transactions = transactions_result.scalars().all()
        logger.info(f"📊 Read {len(transactions)} transactions in session {id(session2)}")

        summary = {
            "accounts": [
                {
                    "id": acc.id,
                    "name": acc.name,
                    "balance": acc.balance,
                }
                for acc in accounts
            ],
            "transactions": [
                {
                    "from": tx.from_account_id,
                    "to": tx.to_account_id,
                    "amount": tx.amount,
                    "status": tx.status,
                }
                for tx in transactions
            ],
        }

        logger.info("✅ Summary generated using 2 concurrent sessions")
        return summary


# ============================================================================
# Example Usage
# ============================================================================


async def example_usage() -> None:
    """Example of sending multi-session tasks to Redis queue."""
    logger.info("\n🚀 Sending multi-session tasks to Taskiq worker...\n")

    # Create accounts
    logger.info("1️⃣ Creating accounts with multiple sessions...")
    task1 = await create_accounts.kiq(
        [
            {"name": "Alice", "balance": 1000.0},
            {"name": "Bob", "balance": 500.0},
            {"name": "Charlie", "balance": 750.0},
        ],
    )
    logger.info(f"  Sent task: {task1.task_id}")

    # Wait a bit for accounts to be created
    await asyncio.sleep(2)

    # Transfer money using multiple sessions
    logger.info("\n2️⃣ Transferring money with concurrent sessions...")
    task2 = await transfer_money_concurrent.kiq(1, 2, 100.0)
    logger.info(f"  Sent task: {task2.task_id}")

    await asyncio.sleep(2)

    # Batch update balances
    logger.info("\n3️⃣ Batch updating balances with separate sessions...")
    task3 = await batch_update_balances.kiq(
        [
            {"account_id": 1, "amount": 50.0},
            {"account_id": 2, "amount": 25.0},
            {"account_id": 3, "amount": 100.0},
        ],
    )
    logger.info(f"  Sent task: {task3.task_id}")

    await asyncio.sleep(2)

    # Get summary using multiple sessions
    logger.info("\n4️⃣ Getting account summary with concurrent reads...")
    task4 = await get_account_summary.kiq()
    logger.info(f"  Sent task: {task4.task_id}")

    logger.info("\n✅ All multi-session tasks sent!")
    logger.info("Check worker terminal to see different session IDs.\n")


if __name__ == "__main__":
    asyncio.run(example_usage())
