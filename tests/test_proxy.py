"""Unit tests for proxy module."""

import pytest

from sqladbx.exceptions import SessionNotInitialisedError
from sqladbx.proxy import db


@pytest.mark.asyncio
async def test_proxy_not_initialized() -> None:
    """Test that accessing session before init raises error."""
    # Reset proxy state
    db.manager = None
    db.SessionFactory = None

    with pytest.raises(SessionNotInitialisedError):
        _ = db.session


@pytest.mark.asyncio
@pytest.mark.usefixtures("initialized_db")
async def test_proxy_initialized() -> None:
    """Test that proxy is initialized correctly."""
    assert db.manager is not None  # noqa: S101
    assert db.SessionFactory is not None  # noqa: S101


@pytest.mark.asyncio
@pytest.mark.usefixtures("initialized_db")
async def test_call_returns_context_manager() -> None:
    """Test that calling db() returns a context manager."""
    context = db()
    assert context is not None  # noqa: S101
    # Don't actually enter context as it needs proper session initialization


@pytest.mark.asyncio
@pytest.mark.usefixtures("initialized_db")
async def test_multi_session_context() -> None:
    """Test multi-session context manager."""
    context = db(multi_sessions=True)
    assert context is not None  # noqa: S101


@pytest.mark.asyncio
@pytest.mark.usefixtures("initialized_db")
async def test_single_session_context() -> None:
    """Test single-session context manager."""
    context = db()
    assert context is not None  # noqa: S101
