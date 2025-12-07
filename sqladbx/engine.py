from sqlalchemy.engine.url import URL
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine


def create_engine(
    db_url: str | URL | None = None,
    custom_engine: AsyncEngine | None = None,
    engine_args: dict | None = None,
) -> AsyncEngine:
    if custom_engine:
        return custom_engine

    if not db_url:
        raise ValueError("db_url or custom_engine must be provided")

    return create_async_engine(db_url, **(engine_args or {}))
