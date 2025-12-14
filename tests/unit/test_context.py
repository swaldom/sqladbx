"""Unit tests for sqladbx.context module.

Tests ContextVar definitions and their default values.
"""

from sqladbx.context import commit_flag, multi_sessions_flag, session_args_override, tracked_sessions


def test_multi_sessions_flag_default() -> None:
    """Test multi_sessions_flag has correct default value."""
    assert multi_sessions_flag.get() is False


def test_commit_flag_default() -> None:
    """Test commit_flag has correct default value."""
    assert commit_flag.get() is False


def test_tracked_sessions_default() -> None:
    """Test tracked_sessions has correct default value."""
    assert tracked_sessions.get() is None


def test_session_args_override_default() -> None:
    """Test session_args_override has correct default value."""
    assert session_args_override.get() is None


def test_multi_sessions_flag_set_reset() -> None:
    """Test multi_sessions_flag can be set and reset."""
    token = multi_sessions_flag.set(True)
    assert multi_sessions_flag.get() is True
    multi_sessions_flag.reset(token)
    assert multi_sessions_flag.get() is False


def test_commit_flag_set_reset() -> None:
    """Test commit_flag can be set and reset."""
    token = commit_flag.set(True)
    assert commit_flag.get() is True
    commit_flag.reset(token)
    assert commit_flag.get() is False


def test_tracked_sessions_set_reset() -> None:
    """Test tracked_sessions can be set and reset."""
    test_set = set()
    token = tracked_sessions.set(test_set)
    assert tracked_sessions.get() is test_set
    tracked_sessions.reset(token)
    assert tracked_sessions.get() is None


def test_session_args_override_set_reset() -> None:
    """Test session_args_override can be set and reset."""
    test_args = {"expire_on_commit": True}
    token = session_args_override.set(test_args)
    assert session_args_override.get() == test_args
    session_args_override.reset(token)
    assert session_args_override.get() is None


def test_context_vars_are_independent() -> None:
    """Test that ContextVars are independent from each other."""
    token1 = multi_sessions_flag.set(True)
    token2 = commit_flag.set(True)

    assert multi_sessions_flag.get() is True
    assert commit_flag.get() is True

    multi_sessions_flag.reset(token1)
    assert multi_sessions_flag.get() is False
    assert commit_flag.get() is True  # Should still be True

    commit_flag.reset(token2)
    assert commit_flag.get() is False
