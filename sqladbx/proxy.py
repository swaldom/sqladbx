"""Database proxy for session management."""

from contextvars import Token
from types import TracebackType

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from sqlalchemy.orm import sessionmaker

from .context import commit_flag, multi_sessions_flag
from .exceptions import SessionNotInitialisedError
from .session import DBSessionManager


class MultiContext:
    """Context manager for multi-session mode."""

    def __init__(
        self,
        manager: DBSessionManager,
        token_flag: Token[bool],
        token_commit: Token[bool],
    ) -> None:
        """Initialize MultiContext.

        Args:
            manager: The session manager.
            token_flag: Token for multi_sessions_flag.
            token_commit: Token for commit_flag.

        """
        self.manager = manager
        self.token_flag = token_flag
        self.token_commit = token_commit

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
        """Exit context and reset flags.

        Args:
            exc_type: Exception type if occurred.
            exc: Exception instance if occurred.
            tb: Traceback if exception occurred.

        """
        multi_sessions_flag.reset(self.token_flag)
        commit_flag.reset(self.token_commit)


class SingleContext:
    """Context manager for single-session mode."""

    def __init__(self, manager: DBSessionManager, token_commit: Token[bool]) -> None:
        """Initialize SingleContext.

        Args:
            manager: The session manager.
            token_commit: Token for commit_flag.

        """
        self.manager = manager
        self.token_commit = token_commit

    async def __aenter__(self) -> DBSessionManager:
        """Enter context and initialize session.

        Returns:
            Session manager instance for access via db.session.

        """
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
        commit_flag.reset(self.token_commit)
        return await self.manager.__aexit__(exc_type, exc, tb)


class DBProxy:
    """Backward-compatible API facade.

    Provides access to database sessions with support for:
    - db.session: Direct session access
    - async with db(): Single-session context
    - async with db(multi_sessions=True): Multi-session context
    """

    def __init__(self) -> None:
        """Initialize DBProxy."""
        self.SessionFactory: object | None = None
        self.manager: DBSessionManager | None = None

    def initialize(self, engine: AsyncEngine, session_args: dict[str, object] | None = None) -> None:
        """Initialize with an AsyncEngine and session configuration.

        Args:
            engine: SQLAlchemy AsyncEngine instance.
            session_args: Additional arguments for sessionmaker.

        """
        self.SessionFactory = sessionmaker(  # type: ignore[call-overload]
            engine,
            class_=AsyncSession,
            expire_on_commit=False,
            **(session_args or {}),
        )
        self.manager = DBSessionManager(self.SessionFactory)  # type: ignore[arg-type]

    @property
    def session(self) -> AsyncSession:
        """Get the current database session.

        Returns:
            Current AsyncSession instance.

        Raises:
            SessionNotInitialisedError: If manager is not initialized.

        """
        if not self.manager:
            raise SessionNotInitialisedError
        return self.manager.get_session()

    def __call__(
        self,
        *,
        commit_on_exit: bool = False,
        multi_sessions: bool = False,
    ) -> MultiContext | SingleContext:
        """Create a context manager for database sessions.

        Args:
            commit_on_exit: Whether to commit on context exit.
            multi_sessions: Whether to enable multi-session mode.

        Returns:
            Async context manager for database session.

        Raises:
            SessionNotInitialisedError: If manager is not initialized.

        """
        if not self.manager:
            raise SessionNotInitialisedError

        if multi_sessions:
            token_flag = multi_sessions_flag.set(True)
            token_commit = commit_flag.set(commit_on_exit)
            return MultiContext(self.manager, token_flag, token_commit)

        token_commit = commit_flag.set(commit_on_exit)
        return SingleContext(self.manager, token_commit)


db = DBProxy()
