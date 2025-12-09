"""Unit tests for context module."""

from contextvars import ContextVar

import pytest

from sqladbx.context import commit_flag, current_session, multi_sessions_flag


@pytest.mark.asyncio
async def test_context_vars_exist() -> None:
    """Test that context variables are properly initialized."""
    assert isinstance(commit_flag, ContextVar)
    assert isinstance(current_session, ContextVar)
    assert isinstance(multi_sessions_flag, ContextVar)


@pytest.mark.asyncio
async def test_context_var_defaults() -> None:
    """Test context variable default values."""
    assert multi_sessions_flag.get() is False
    assert commit_flag.get() is False
    assert current_session.get() is None


@pytest.mark.asyncio
async def test_context_var_set_and_reset() -> None:
    """Test setting and resetting context variables."""
    token = multi_sessions_flag.set(True)
    assert multi_sessions_flag.get() is True

    multi_sessions_flag.reset(token)
    assert multi_sessions_flag.get() is False
