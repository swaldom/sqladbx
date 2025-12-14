"""sqladbx - SQLAlchemy database context manager for async applications.

This library provides tools for managing SQLAlchemy async sessions in various
async frameworks like FastAPI, Taskiq, Temporal, and Litestar.

Basic usage with FastAPI:
    >>> from fastapi import FastAPI
    >>> from sqladbx import db, SQLAlchemyMiddleware
    >>>
    >>> app = FastAPI()
    >>> app.add_middleware(SQLAlchemyMiddleware, db_url="postgresql+asyncpg://...")
    >>>
    >>> @app.on_event("startup")
    >>> async def startup():
    ...     # Create tables using db.engine
    ...     if db.engine:
    ...         async with db.engine.begin() as conn:
    ...             await conn.run_sync(Base.metadata.create_all)
    >>>
    >>> @app.get("/users")
    >>> async def list_users():
    ...     # Middleware creates session automatically - use db.session directly
    ...     result = await db.session.execute(select(User))
    ...     return result.scalars().all()
    >>>
    >>> @app.post("/users")
    >>> async def create_user(name: str):
    ...     user = User(name=name)
    ...     db.session.add(user)
    ...     await db.session.commit()  # Explicit commit for writes
    ...     return user

Usage without middleware (Taskiq, Temporal):
    >>> from sqladbx import db
    >>>
    >>> db.initialize(create_async_engine("postgresql+asyncpg://..."))
    >>>
    >>> async with db():
    ...     result = await db.session.execute(select(User))
    ...     return result.scalars().all()

Multiple databases:
    >>> from sqladbx import create_db, create_db_middleware
    >>>
    >>> replica_db = create_db()
    >>> ReplicaMiddleware = create_db_middleware()
    >>>
    >>> app.add_middleware(SQLAlchemyMiddleware, db_url="postgresql+asyncpg://primary")
    >>> app.add_middleware(ReplicaMiddleware, db_url="postgresql+asyncpg://replica", db_proxy=replica_db)
"""

from .exceptions import MissingSessionError, SessionNotInitializedError
from .middleware import SQLAlchemyMiddleware, create_db_middleware
from .proxy import DBProxy, db

__version__ = "0.0.4"


def create_db() -> DBProxy:
    """Create a new isolated database proxy instance.

    This function creates a new DBProxy instance with its own session management,
    allowing multiple independent database contexts in the same application.

    Returns:
        A new DBProxy instance for managing database sessions.

    Example:
        >>> from sqladbx import create_db, create_db_middleware
        >>> from sqlalchemy.ext.asyncio import create_async_engine
        >>>
        >>> # Create a separate database proxy for replica
        >>> replica_db = create_db()
        >>> replica_engine = create_async_engine("postgresql+asyncpg://replica")
        >>> replica_db.initialize(replica_engine)
        >>>
        >>> # Use in your application
        >>> async with replica_db():
        ...     result = await replica_db.session.execute(select(User))
        ...     return result.scalars().all()
    """
    return DBProxy()


def create_middleware_and_db() -> tuple[type[SQLAlchemyMiddleware], DBProxy]:
    """Create a middleware class and database proxy pair.

    This function creates a new isolated database proxy and its corresponding
    middleware class with the db_proxy pre-bound. This is useful for managing
    multiple databases in the same application with a single function call.

    Returns:
        A tuple of (Middleware class, DBProxy instance).

    Example:
        >>> from sqladbx import create_middleware_and_db
        >>>
        >>> ReplicaMiddleware, replica_db = create_middleware_and_db()
        >>>
        >>> # No need to pass db_proxy - it's already bound!
        >>> app.add_middleware(
        ...     ReplicaMiddleware,
        ...     db_url="postgresql+asyncpg://replica"
        ... )
        >>>
        >>> @app.get("/users-cached")
        >>> async def list_users_cached():
        ...     async with replica_db():
        ...         result = await replica_db.session.execute(select(User))
        ...         return result.scalars().all()
    """
    db_proxy = create_db()
    middleware = create_db_middleware(db_proxy)
    return middleware, db_proxy


__all__ = [
    "DBProxy",
    "MissingSessionError",
    "SQLAlchemyMiddleware",
    "SessionNotInitializedError",
    "__version__",
    "create_db",
    "create_db_middleware",
    "create_middleware_and_db",
    "db",
]
