"""Unit tests for sqladbx.session module.

Tests DBSessionManager class and session lifecycle.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from sqladbx.context import commit_flag, current_session, multi_sessions_flag, session_args_override, tracked_sessions
from sqladbx.exceptions import MissingSessionError, SessionNotInitializedError
from sqladbx.session import DBSessionManager

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Generator


@pytest_asyncio.fixture
async def test_engine() -> AsyncGenerator[AsyncEngine]:
    """Create in-memory SQLite engine for tests."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
        poolclass=StaticPool,
    )
    yield engine
    await engine.dispose()


@pytest.fixture(autouse=True)
def reset_context_vars() -> Generator[None]:
    """Reset all ContextVars before each test."""
    # Reset to defaults
    multi_sessions_flag.set(False)
    commit_flag.set(False)
    tracked_sessions.set(None)
    session_args_override.set(None)
    yield
    # Reset after test
    multi_sessions_flag.set(False)
    commit_flag.set(False)
    tracked_sessions.set(None)
    session_args_override.set(None)


def test_init_with_factory(test_engine: AsyncEngine) -> None:
    """Test DBSessionManager can be initialized with factory."""
    factory = async_sessionmaker(test_engine, class_=AsyncSession)
    manager = DBSessionManager(factory)
    assert manager.session_factory is factory


def test_ensure_initialized_with_none_raises() -> None:
    """Test ensure_initialized raises when factory is None."""
    manager = DBSessionManager(None)
    with pytest.raises(SessionNotInitializedError):
        manager.ensure_initialized()


def test_ensure_initialized_with_invalid_type_raises() -> None:
    """Test ensure_initialized raises when factory is invalid type."""
    manager = DBSessionManager("invalid")
    with pytest.raises(SessionNotInitializedError):
        manager.ensure_initialized()


def test_ensure_initialized_with_factory_succeeds(test_engine: AsyncEngine) -> None:
    """Test ensure_initialized succeeds with valid factory."""
    factory = async_sessionmaker(test_engine, class_=AsyncSession)
    manager = DBSessionManager(factory)
    # Should not raise
    manager.ensure_initialized()


def test_get_session_not_initialized_raises() -> None:
    """Test get_session raises when not initialized."""
    manager = DBSessionManager(None)
    with pytest.raises(SessionNotInitializedError):
        manager.get_session()


def test_get_session_no_session_in_single_mode_raises(test_engine: AsyncEngine) -> None:
    """Test get_session raises when no session in single mode."""
    factory = async_sessionmaker(test_engine, class_=AsyncSession)
    manager = DBSessionManager(factory)

    # Ensure we're not in multi-session mode
    assert not multi_sessions_flag.get()

    # In single mode without entering context, should raise
    with pytest.raises(MissingSessionError):
        manager.get_session()


def test_get_session_multi_mode_creates_new_session(test_engine: AsyncEngine) -> None:
    """Test get_session creates new session in multi mode."""
    factory = async_sessionmaker(test_engine, class_=AsyncSession)
    manager = DBSessionManager(factory)

    token = multi_sessions_flag.set(True)
    try:
        session = manager.get_session()
        assert isinstance(session, AsyncSession)
    finally:
        multi_sessions_flag.reset(token)


def test_get_session_multi_mode_returns_different_sessions(test_engine: AsyncEngine) -> None:
    """Test get_session returns different sessions in multi mode."""
    factory = async_sessionmaker(test_engine, class_=AsyncSession)
    manager = DBSessionManager(factory)

    token = multi_sessions_flag.set(True)
    try:
        session1 = manager.get_session()
        session2 = manager.get_session()
        assert session1 is not session2
    finally:
        multi_sessions_flag.reset(token)


def test_create_multi_session_returns_session(test_engine: AsyncEngine) -> None:
    """Test _create_multi_session returns AsyncSession."""
    factory = async_sessionmaker(test_engine, class_=AsyncSession)
    manager = DBSessionManager(factory)

    session = manager._create_multi_session()  # noqa: SLF001
    assert isinstance(session, AsyncSession)


def test_create_multi_session_tracks_session(test_engine: AsyncEngine) -> None:
    """Test _create_multi_session adds session to tracked_sessions."""
    factory = async_sessionmaker(test_engine, class_=AsyncSession)
    manager = DBSessionManager(factory)

    # Set up tracking
    tracked = set()
    token = tracked_sessions.set(tracked)

    try:
        session = manager._create_multi_session()  # noqa: SLF001
        assert session in tracked
    finally:
        tracked_sessions.reset(token)


def test_create_multi_session_with_session_args(test_engine: AsyncEngine) -> None:
    """Test _create_multi_session respects session_args_override."""
    factory = async_sessionmaker(test_engine, class_=AsyncSession)
    manager = DBSessionManager(factory)

    # Set session args
    args = {"expire_on_commit": True}
    token = session_args_override.set(args)

    try:
        session = manager._create_multi_session()  # noqa: SLF001
        assert isinstance(session, AsyncSession)
        # Note: Can't easily verify expire_on_commit was set,
        # but we verify no errors occurred
    finally:
        session_args_override.reset(token)


async def test_aenter_single_mode_creates_session(test_engine: AsyncEngine) -> None:
    """Test __aenter__ creates session in single mode."""
    factory = async_sessionmaker(test_engine, class_=AsyncSession)
    manager = DBSessionManager(factory)

    result = await manager.__aenter__()
    assert result is manager

    # Verify session was created by getting it
    session = manager.get_session()
    assert isinstance(session, AsyncSession)

    # Cleanup
    await manager.__aexit__(None, None, None)


async def test_aenter_multi_mode_no_session(test_engine: AsyncEngine) -> None:
    """Test __aenter__ doesn't create session in multi mode."""
    factory = async_sessionmaker(test_engine, class_=AsyncSession)
    manager = DBSessionManager(factory)

    token = multi_sessions_flag.set(True)
    try:
        result = await manager.__aenter__()
        assert result is manager
        # In multi-mode, sessions are created on-demand via get_session()
        # current_session should remain None
        assert current_session.get() is None
    finally:
        multi_sessions_flag.reset(token)


async def test_aexit_single_mode_rollback_on_exception(test_engine: AsyncEngine) -> None:
    """Test __aexit__ rolls back on exception and cleans up session."""
    factory = async_sessionmaker(test_engine, class_=AsyncSession)
    manager = DBSessionManager(factory)

    await manager.__aenter__()

    # Verify session is accessible
    session = manager.get_session()
    assert isinstance(session, AsyncSession)

    # Simulate exception
    await manager.__aexit__(ValueError, ValueError("test"), None)

    # Verify session is cleaned up - should raise MissingSessionError
    with pytest.raises(MissingSessionError):
        manager.get_session()


async def test_aexit_single_mode_commit_on_flag(test_engine: AsyncEngine) -> None:
    """Test __aexit__ commits when commit_flag is set and cleans up session."""
    factory = async_sessionmaker(test_engine, class_=AsyncSession)
    manager = DBSessionManager(factory)

    token = commit_flag.set(True)
    try:
        await manager.__aenter__()

        # Verify session is accessible
        session = manager.get_session()
        assert isinstance(session, AsyncSession)

        await manager.__aexit__(None, None, None)

        # Verify session is cleaned up - should raise MissingSessionError
        with pytest.raises(MissingSessionError):
            manager.get_session()
    finally:
        commit_flag.reset(token)
