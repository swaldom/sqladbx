"""Context variables for session and mode management."""

from contextvars import ContextVar

from sqlalchemy.ext.asyncio import AsyncSession

# multi-session mode flag
multi_sessions_flag: ContextVar[bool] = ContextVar(
    "multi_sessions_flag",
    default=False,
)

# commit on exit flag
commit_flag: ContextVar[bool] = ContextVar("commit_flag", default=False)

# tracked sessions for multi-session mode cleanup
tracked_sessions: ContextVar[set[AsyncSession] | None] = ContextVar(
    "tracked_sessions",
    default=None,
)

# session_args override for single-session mode
session_args_override: ContextVar[dict[str, object] | None] = ContextVar(
    "session_args_override",
    default=None,
)
