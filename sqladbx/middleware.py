"""SQLAlchemy middleware for Starlette."""

from collections.abc import Awaitable, Callable
from typing import Any

from sqlalchemy.engine.url import URL
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

from .proxy import DBProxy, db


class SQLAlchemyMiddleware(BaseHTTPMiddleware):
    """Middleware to initialize and manage SQLAlchemy async sessions."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        db_url: str | URL | None = None,
        custom_engine: AsyncEngine | None = None,
        engine_args: dict[str, object] | None = None,
        session_args: dict[str, object] | None = None,
        commit_on_exit: bool = False,
        db_proxy: DBProxy | None = None,
    ) -> None:
        """Initialize SQLAlchemyMiddleware.

        Args:
            app: Starlette ASGI application.
            db_url: Database URL for connection.
            custom_engine: Pre-configured AsyncEngine to use instead.
            engine_args: Additional arguments for create_async_engine.
            session_args: Additional arguments for sessionmaker.
            commit_on_exit: Whether to commit on context exit.
            db_proxy: DBProxy instance to use. If None, uses default db.

        """
        super().__init__(app)
        self.commit_on_exit = commit_on_exit
        self.db_proxy = db_proxy or db

        # Create or use provided engine
        if custom_engine:
            engine = custom_engine
        elif db_url:
            engine = create_async_engine(db_url, **(engine_args or {}))
        else:
            msg = "Either db_url or custom_engine must be provided"
            raise ValueError(msg)

        self.db_proxy.initialize(engine, session_args=session_args)

    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        """Process request with database session context.

        Args:
            request: Incoming HTTP request.
            call_next: Next middleware/route handler.

        Returns:
            HTTP response.

        """
        # Wrap request in database session context
        # This allows route handlers to use db.session directly without async with db()
        async with self.db_proxy(commit_on_exit=self.commit_on_exit):
            return await call_next(request)


def create_db_middleware(db_proxy: DBProxy | None = None) -> type[SQLAlchemyMiddleware]:
    """Factory function to create a middleware class for a specific database.

    Creates a new middleware class with an optional pre-configured db_proxy.
    This is useful for managing multiple databases - each middleware gets
    its own unique class type and optionally its own db_proxy.

    Args:
        db_proxy: Optional DBProxy instance to bind to this middleware.
                 If provided, you don't need to pass db_proxy when adding middleware.
                 If None, you must pass db_proxy when adding middleware to the app.

    Returns:
        A new SQLAlchemyMiddleware class.

    Examples:
        >>> # Option 1: Pre-bind db_proxy (recommended for multiple databases)
        >>> replica_db = DBProxy()
        >>> ReplicaMiddleware = create_db_middleware(replica_db)
        >>> app.add_middleware(
        ...     ReplicaMiddleware,
        ...     db_url="postgresql+asyncpg://replica"
        ... )
        >>>
        >>> # Option 2: Pass db_proxy later (more flexible)
        >>> ReplicaMiddleware = create_db_middleware()
        >>> app.add_middleware(
        ...     ReplicaMiddleware,
        ...     db_url="postgresql+asyncpg://...",
        ...     db_proxy=replica_db
        ... )
    """

    class CustomDBMiddleware(SQLAlchemyMiddleware):
        """Custom middleware for multiple databases.

        This class is dynamically created to ensure each middleware
        has a unique type, allowing Starlette to treat them as separate
        middleware instances.
        """

        def __init__(self, app: ASGIApp, **kwargs: Any) -> None:
            """Initialize middleware with bound db_proxy if available.

            Args:
                app: ASGI application.
                **kwargs: Middleware configuration parameters.
            """
            # Use bound db_proxy from closure if available and not overridden
            if db_proxy is not None and "db_proxy" not in kwargs:
                kwargs["db_proxy"] = db_proxy
            super().__init__(app, **kwargs)

    return CustomDBMiddleware
