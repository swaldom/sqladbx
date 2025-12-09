"""SQLAlchemy middleware for Starlette."""

from collections.abc import Awaitable, Callable

from sqlalchemy.engine.url import URL
from sqlalchemy.ext.asyncio import AsyncEngine
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

from .engine import create_engine
from .proxy import DBProxy, db


class SQLAlchemyMiddleware(BaseHTTPMiddleware):
    """Middleware to initialize and manage SQLAlchemy async sessions."""

    def __init__(  # noqa: PLR0913
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

        engine = create_engine(db_url, custom_engine, engine_args)
        self.db_proxy.initialize(engine, session_args)

    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        """Process request with database session context.

        Args:
            request: Incoming HTTP request.
            call_next: Next middleware/route handler.

        Returns:
            HTTP response.

        """
        # Don't wrap in context manager - route handlers manage their own context
        # This prevents ContextVar token reuse errors when multiple proxies are used
        return await call_next(request)


def create_db_middleware() -> type[SQLAlchemyMiddleware]:
    """Create a middleware class for a specific database.

    Returns a simple middleware class - db_proxy and other params are passed
    when adding the middleware to the app.

    Returns:
        A SQLAlchemyMiddleware class.

    Example:
        >>> ReplicaMiddleware = create_db_middleware()
        >>> app.add_middleware(
        ...     ReplicaMiddleware,
        ...     db_url="postgresql+asyncpg://...",
        ...     db_proxy=replica_db,
        ...     db_name="replica_db",
        ...     engine_args={"echo": True}
        ... )

    """

    class CustomDBMiddleware(SQLAlchemyMiddleware):
        """Custom middleware for multiple databases."""

    return CustomDBMiddleware
