"""Context variables for session and mode management."""

from contextvars import ContextVar

# multi-session mode flag
multi_sessions_flag: ContextVar[bool] = ContextVar(
    "multi_sessions_flag",
    default=False,
)

# commit on exit flag
commit_flag: ContextVar[bool] = ContextVar("commit_flag", default=False)
