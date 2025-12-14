"""Database session management."""

from types import TracebackType

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from .context import commit_flag, current_session, multi_sessions_flag, session_args_override, tracked_sessions
from .exceptions import MissingSessionError, SessionNotInitializedError


class DBSessionManager:
    """Manages async session lifecycle for both shared-context and multi-session modes."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        """Initialize DBSessionManager.

        Args:
            session_factory: SQLAlchemy async_sessionmaker instance.

        """
        self.session_factory: async_sessionmaker[AsyncSession] = session_factory

    def ensure_initialized(self) -> None:
        """Ensure session factory is initialized.

        Raises:
            SessionNotInitializedError: If session_factory is not an async_sessionmaker.

        """
        if not isinstance(self.session_factory, async_sessionmaker):
            raise SessionNotInitializedError

    def get_session(self) -> AsyncSession:
        """Return the session depending on mode.

        Returns:
            AsyncSession instance.

        Raises:
            SessionNotInitializedError: If not initialized.
            MissingSessionError: If no session in single-session mode.

        """
        self.ensure_initialized()

        if multi_sessions_flag.get():
            return self._create_multi_session()

        # Use ContextVar for task-isolated session
        session = current_session.get()
        if session is None:
            raise MissingSessionError
        return session

    def _create_multi_session(self) -> AsyncSession:
        """Create a new session for multi-session mode.

        Always returns a new session per call.
        Sessions are tracked and cleaned up in __aexit__.
        Respects session_args_override from ContextVar if set.

        Returns:
            AsyncSession instance.

        """
        # Create session with optional args from ContextVar
        session = self.session_factory(**(session_args_override.get() or {}))

        # Track the session for cleanup in __aexit__
        tracked = tracked_sessions.get()
        if tracked is not None:
            tracked.add(session)

        return session

    async def __aenter__(self) -> "DBSessionManager":
        """Enter async context and initialize session.

        Returns:
            Self instance.

        """
        self.ensure_initialized()

        if multi_sessions_flag.get():
            # multi-session mode already enabled
            return self

        # single-session mode - store session in ContextVar for task isolation
        session = self.session_factory(**(session_args_override.get() or {}))
        current_session.set(session)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        """Exit async context and cleanup session.

        Args:
            exc_type: Exception type if occurred.
            exc_value: Exception instance if occurred.
            tb: Traceback if exception occurred.

        """
        if multi_sessions_flag.get():
            # Multi-session mode - cleanup is handled in MultiContext.__aexit__
            return

        # Get session from ContextVar
        session = current_session.get()
        if session is not None:
            try:
                if exc_type:
                    await session.rollback()
                elif commit_flag.get():
                    await session.commit()
            finally:
                await session.close()
                current_session.set(None)
