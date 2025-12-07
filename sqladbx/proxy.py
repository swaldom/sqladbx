from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.orm import sessionmaker

from .context import commit_flag, multi_sessions_flag
from .exceptions import SessionNotInitialisedError
from .session import AsyncSession, DBSessionManager


class DBProxy:
    """
    Backward-compatible API facade:
    - db.session
    - async with db()
    - async with db(multi_sessions=True)
    """

    def __init__(self):
        self.SessionFactory: sessionmaker | None = None
        self.manager: DBSessionManager | None = None

    def initialize(self, engine: AsyncEngine, session_args: dict | None = None):
        self.SessionFactory = sessionmaker(
            engine,
            class_=AsyncSession,
            expire_on_commit=False,
            **(session_args or {}),
        )
        self.manager = DBSessionManager(self.SessionFactory)

    @property
    def session(self):
        if not self.manager:
            raise SessionNotInitialisedError
        return self.manager.get_session()

    def __call__(self, *, commit_on_exit=False, multi_sessions=False, session_args=None):
        if not self.manager:
            raise SessionNotInitialisedError

        if multi_sessions:
            token_flag = multi_sessions_flag.set(True)
            token_commit = commit_flag.set(commit_on_exit)

            class MultiContext:
                async def __aenter__(inner_self):
                    return self.manager

                async def __aexit__(inner_self, exc_type, exc, tb):
                    multi_sessions_flag.reset(token_flag)
                    commit_flag.reset(token_commit)

            return MultiContext()
        token_commit = commit_flag.set(commit_on_exit)

        class SingleContext:
            async def __aenter__(inner_self):
                return await self.manager.__aenter__()

            async def __aexit__(inner_self, exc_type, exc, tb):
                commit_flag.reset(token_commit)
                return await self.manager.__aexit__(exc_type, exc, tb)

        return SingleContext()


db = DBProxy()
