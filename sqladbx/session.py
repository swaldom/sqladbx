"""Database session management."""

import asyncio
from types import TracebackType
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker

from .context import commit_flag, multi_sessions_flag
from .exceptions import MissingSessionError, SessionNotInitialisedError


class DBSessionManager:
    """Manages async session lifecycle for both shared-context and multi-session modes."""

    def __init__(self, session_factory: sessionmaker[AsyncSession] | None) -> None:  # type: ignore[type-var]
        """Initialize DBSessionManager.

        Args:
            session_factory: SQLAlchemy sessionmaker instance.

        """
        self.SessionFactory: Any = session_factory
        self._session: AsyncSession | None = None

    def ensure_initialized(self) -> None:
        """Ensure session factory is initialized.

        Raises:
            SessionNotInitialisedError: If SessionFactory is not a sessionmaker.

        """
        if not isinstance(self.SessionFactory, sessionmaker):
            raise SessionNotInitialisedError

    def get_session(self) -> AsyncSession:
        """Return the session depending on mode.

        Returns:
            AsyncSession instance.

        Raises:
            SessionNotInitialisedError: If not initialized.
            MissingSessionError: If no session in single-session mode.

        """
        self.ensure_initialized()

        if multi_sessions_flag.get():
            return self._create_multi_session()
        if self._session is None:
            raise MissingSessionError
        return self._session

    def _create_multi_session(self) -> AsyncSession:
        """Create a new session for multi-session mode.

        Always returns a new session per call.
        Cleanup is guaranteed after task completion.

        Returns:
            AsyncSession instance.

        """
        session: AsyncSession = self.SessionFactory()

        async def cleanup() -> None:
            """Cleanup session after task completion."""
            try:
                if commit_flag.get():
                    await session.commit()
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()

        task = asyncio.current_task()
        if task:
            task.add_done_callback(lambda _: asyncio.create_task(cleanup()))

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

        # single-session mode
        self._session = self.SessionFactory()
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
            # multi-session cleanup handled by task callback
            return

        if self._session is not None:
            try:
                if exc_type:
                    await self._session.rollback()
                elif commit_flag.get():
                    await self._session.commit()
            finally:
                await self._session.close()
                self._session = None
