from contextvars import ContextVar

from sqlalchemy.ext.asyncio import AsyncSession

# Stores session for non-multi context
current_session: ContextVar[AsyncSession | None] = ContextVar("current_session", default=None)

# multi-session mode flag
multi_sessions_flag: ContextVar[bool] = ContextVar("multi_sessions_flag", default=False)

# commit on exit flag
commit_flag: ContextVar[bool] = ContextVar("commit_flag", default=False)
