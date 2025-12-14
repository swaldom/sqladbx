"""Database proxy for session management."""

import warnings
from contextvars import Token
from types import TracebackType
from typing import Any

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from .context import commit_flag, multi_sessions_flag, session_args_override, tracked_sessions
from .exceptions import SessionNotInitializedError
from .session import DBSessionManager


class SingleContext:
    """Context manager for single-session mode."""

    def __init__(
        self,
        manager: DBSessionManager,
        token_commit: Token[bool],
        token_session_args: Token[dict[str, object] | None],
    ) -> None:
        """Initialize SingleContext.

        Args:
            manager: The session manager.
            token_commit: Token for commit_flag.
            token_session_args: Token for session_args_override.

        """
        self.manager = manager
        self.token_commit = token_commit
        self.token_session_args = token_session_args

    async def __aenter__(self) -> DBSessionManager:
        """Enter context and initialize session.

        Returns:
            Session manager instance for access via db.session.

        """
        # Use manager's __aenter__ which reads session_args from ContextVar
        return await self.manager.__aenter__()

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        """Exit context and cleanup session.

        Args:
            exc_type: Exception type if occurred.
            exc: Exception instance if occurred.
            tb: Traceback if exception occurred.

        """
        try:
            return await self.manager.__aexit__(exc_type, exc, tb)
        finally:
            # Reset context vars
            session_args_override.reset(self.token_session_args)
            commit_flag.reset(self.token_commit)


class MultiContext:
    """Context manager for multi-session mode."""

    def __init__(
        self,
        manager: DBSessionManager,
        token_flag: Token[bool],
        token_commit: Token[bool],
        token_tracked: Token[set[AsyncSession] | None],
        token_session_args: Token[dict[str, object] | None],
    ) -> None:
        """Initialize MultiContext.

        Args:
            manager: The session manager.
            token_flag: Token for multi_sessions_flag.
            token_commit: Token for commit_flag.
            token_tracked: Token for tracked_sessions.
            token_session_args: Token for session_args_override.

        """
        self.manager = manager
        self.token_flag = token_flag
        self.token_commit = token_commit
        self.token_tracked = token_tracked
        self.token_session_args = token_session_args

    async def __aenter__(self) -> object:
        """Enter context.

        Returns:
            Session manager instance.

        """
        return self.manager

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        """Exit context and cleanup all tracked sessions.

        Args:
            exc_type: Exception type if occurred.
            exc: Exception instance if occurred.
            tb: Traceback if exception occurred.

        """
        # Clean up all tracked sessions
        tracked = tracked_sessions.get()
        if tracked:
            cleanup_errors: list[Exception] = []
            for session in tracked:
                try:
                    if exc_type is not None:
                        await session.rollback()
                    elif commit_flag.get():
                        try:
                            await session.commit()
                        except Exception as commit_error:
                            warnings.warn(
                                f"Failed to commit in multi_sessions: {commit_error}",
                                RuntimeWarning,
                                stacklevel=2,
                            )
                            await session.rollback()
                            cleanup_errors.append(commit_error)
                except Exception as cleanup_error:
                    warnings.warn(
                        f"Failed to rollback session in multi_sessions: {cleanup_error}",
                        RuntimeWarning,
                        stacklevel=2,
                    )
                    cleanup_errors.append(cleanup_error)
                finally:
                    try:
                        await session.close()
                    except Exception as close_error:
                        warnings.warn(
                            f"Failed to close session in multi_session: {close_error}",
                            ResourceWarning,
                            stacklevel=2,
                        )
                        cleanup_errors.append(close_error)

            if cleanup_errors and exc_type is None:
                warnings.warn(
                    f"Encountered {len(cleanup_errors)} error(s) during session cleanup",
                    RuntimeWarning,
                    stacklevel=2,
                )

        # Reset context vars
        tracked_sessions.reset(self.token_tracked)
        multi_sessions_flag.reset(self.token_flag)
        commit_flag.reset(self.token_commit)
        session_args_override.reset(self.token_session_args)


class DBProxy:
    """Backward-compatible API facade.

    Provides access to database sessions with support for:
    - db.session: Direct session access
    - db.engine: Access to AsyncEngine for DDL operations
    - async with db(): Single-session context
    - async with db(multi_sessions=True): Multi-session context
    """

    def __init__(self) -> None:
        """Initialize DBProxy."""
        self.session_factory: async_sessionmaker[AsyncSession] | None = None
        self.manager: DBSessionManager | None = None
        self.engine: AsyncEngine | None = None

    def initialize(
        self,
        engine: AsyncEngine | None = None,
        *,
        engine_args: dict[str, object] | None = None,
        session_args: dict[str, object] | None = None,
        db_url: str | None = None,
    ) -> None:
        """Initialize with database connection.

        Provide either engine (positional) or db_url (keyword).

        Args:
            engine: Pre-configured AsyncEngine (optional positional argument).
            engine_args: Additional arguments for create_async_engine (only with db_url).
            session_args: Additional arguments for sessionmaker.
                          Default: {"expire_on_commit": False} for better async performance.
                          Override by passing {"expire_on_commit": True} if needed.
            db_url: Database URL for connection (keyword-only).

        Raises:
            ValueError: If neither engine nor db_url is provided.

        Note:
            By default, expire_on_commit is set to False for better async performance.
            This prevents SQLAlchemy from expiring objects after commit, which would
            require additional database queries to refresh them. Override this by
            passing session_args={"expire_on_commit": True} if you need the default
            SQLAlchemy behavior.

        Examples:
            >>> # Option 1: Using pre-configured engine (most explicit)
            >>> engine = create_async_engine("postgresql+asyncpg://...")
            >>> db.initialize(engine)
            >>>
            >>> # Option 2: Using db_url (recommended for simple cases)
            >>> db.initialize(db_url="postgresql+asyncpg://localhost/mydb")
            >>>
            >>> # Option 3: With engine args
            >>> db.initialize(
            ...     db_url="postgresql+asyncpg://localhost/mydb",
            ...     engine_args={"echo": True, "pool_size": 10}
            ... )
            >>>
            >>> # Option 4: Override expire_on_commit
            >>> db.initialize(
            ...     db_url="postgresql+asyncpg://localhost/mydb",
            ...     session_args={"expire_on_commit": True}
            ... )

        """
        # Create or use provided engine
        if engine:
            self.engine = engine
        elif db_url:
            self.engine = create_async_engine(db_url, **(engine_args or {}))
        else:
            msg = "Either engine or db_url must be provided"
            raise ValueError(msg)

        # Set default expire_on_commit=False for better async performance
        # User can override by passing session_args={"expire_on_commit": True}
        final_session_args: dict[str, Any] = session_args or {}
        if "expire_on_commit" not in final_session_args:
            final_session_args = {**final_session_args, "expire_on_commit": False}

        self.session_factory = async_sessionmaker(
            self.engine,
            class_=AsyncSession,
            **final_session_args,
        )
        self.manager = DBSessionManager(self.session_factory)

    async def dispose(self) -> None:
        """Dispose engine and cleanup all resources.

        Optional but recommended for:
        - Graceful shutdown in production
        - Tests (prevents file descriptor leaks)
        - Multi-tenant applications with dynamic engines

        Not strictly required for simple applications where the engine
        lives for the entire process lifetime. The OS will close connections
        when the process terminates.

        Examples:
            >>> # In FastAPI lifespan (recommended)
            >>> @asynccontextmanager
            >>> async def lifespan(app: FastAPI):
            ...     db.initialize(db_url="postgresql+asyncpg://...")
            ...     yield
            ...     await db.dispose()  # Graceful shutdown
            >>>
            >>> # In tests (required to prevent file descriptor leaks)
            >>> async def test_something():
            ...     db.initialize(db_url="sqlite+aiosqlite:///:memory:")
            ...     # ... test code
            ...     await db.dispose()  # Cleanup

        """
        if self.engine:
            await self.engine.dispose()
            self.engine = None
            self.session_factory = None
            self.manager = None

    @property
    def session(self) -> AsyncSession:
        """Get the current database session.

        Returns:
            Current AsyncSession instance.

        Raises:
            SessionNotInitializedError: If manager is not initialized.

        """
        if not self.manager:
            raise SessionNotInitializedError
        return self.manager.get_session()

    def __call__(
        self,
        *,
        commit_on_exit: bool = False,
        multi_sessions: bool = False,
        session_args: dict[str, object] | None = None,
    ) -> MultiContext | SingleContext:
        """Create a context manager for database sessions.

        Args:
            commit_on_exit: Whether to commit on context exit.
            multi_sessions: Whether to enable multi-session mode.
            session_args: Additional session arguments to override defaults.
                         Use this to override any session parameter like expire_on_commit.
                         Works in both single-session and multi-session modes.

        Returns:
            Async context manager for database session.

        Raises:
            SessionNotInitializedError: If manager is not initialized.

        Note:
            In multi-session mode, session_args applies to ALL sessions created
            within the context. For global configuration, use db.initialize(session_args=...)

        Examples:
            >>> # Single-session with custom args
            >>> async with db(session_args={"expire_on_commit": True}):
            ...     result = await db.session.execute(select(User))
            >>>
            >>> # Multi-session with custom args (applies to all sessions)
            >>> async with db(multi_sessions=True, session_args={"expire_on_commit": True}):
            ...     # Each db.session call creates new session with expire_on_commit=True
            ...     result1 = await db.session.execute(select(User))
            ...     result2 = await db.session.execute(select(Post))

        """
        if not self.manager:
            raise SessionNotInitializedError

        # Set session_args in ContextVar for both modes
        if multi_sessions:
            token_flag = multi_sessions_flag.set(True)
            token_commit = commit_flag.set(commit_on_exit)
            token_tracked = tracked_sessions.set(set())
            token_session_args = session_args_override.set(session_args)
            return MultiContext(self.manager, token_flag, token_commit, token_tracked, token_session_args)

        # Single-session mode with optional session_args
        token_commit = commit_flag.set(commit_on_exit)
        token_session_args = session_args_override.set(session_args)
        return SingleContext(self.manager, token_commit, token_session_args)


db = DBProxy()
