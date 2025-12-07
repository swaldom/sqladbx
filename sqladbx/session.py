import asyncio

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker

from .context import commit_flag, current_session, multi_sessions_flag
from .exceptions import MissingSessionError, SessionNotInitialisedError


class DBSessionManager:
    """
    Manages async session lifecycle for both shared-context mode
    and multi-session parallel mode.
    """

    def __init__(self, SessionFactory: sessionmaker | None):
        self.SessionFactory = SessionFactory

    def ensure_initialized(self):
        if not isinstance(self.SessionFactory, sessionmaker):
            raise SessionNotInitialisedError

    def get_session(self) -> AsyncSession:
        """
        Returns the session depending on mode.
        """
        self.ensure_initialized()

        if multi_sessions_flag.get():
            return self._create_multi_session()
        sess = current_session.get()
        if sess is None:
            raise MissingSessionError
        return sess

    def _create_multi_session(self) -> AsyncSession:
        """
        Always returns a new session per call.
        Cleanup guaranteed after task completion.
        """
        session = self.SessionFactory()

        async def cleanup():
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

    async def __aenter__(self):
        self.ensure_initialized()

        if multi_sessions_flag.get():
            # multi-session mode already enabled
            return self

        # single-session mode
        session = self.SessionFactory()
        self._session_token = current_session.set(session)
        return self

    async def __aexit__(self, exc_type, exc_value, tb):
        if multi_sessions_flag.get():
            # multi-session cleanup handled by task callback
            return

        session = current_session.get()
        try:
            if exc_type:
                await session.rollback()
            elif commit_flag.get():
                await session.commit()
        finally:
            await session.close()
            current_session.reset(self._session_token)
