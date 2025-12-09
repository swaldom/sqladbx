"""SQLAlchemy async engine creation."""

from sqlalchemy.engine.url import URL
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine


def create_engine(
    db_url: str | URL | None = None,
    custom_engine: AsyncEngine | None = None,
    engine_args: dict[str, object] | None = None,
) -> AsyncEngine:
    """Create an async SQLAlchemy engine.

    Args:
        db_url: Database URL for connection.
        custom_engine: Pre-configured AsyncEngine to use instead.
        engine_args: Additional arguments to pass to create_async_engine.

    Returns:
        Configured AsyncEngine instance.

    Raises:
        ValueError: If neither db_url nor custom_engine is provided.

    """
    if custom_engine:
        return custom_engine

    if not db_url:
        msg = "db_url or custom_engine must be provided"
        raise ValueError(msg)

    return create_async_engine(db_url, **(engine_args or {}))
