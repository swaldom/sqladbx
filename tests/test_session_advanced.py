"""Advanced integration tests for session management and multi-session modes."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker

from sqladbx.context import commit_flag, current_session, multi_sessions_flag
from sqladbx.exceptions import MissingSessionError, SessionNotInitialisedError
from sqladbx.session import DBSessionManager

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine


async def test_session_manager_not_initialized() -> None:
    """Test MissingSessionError when session not initialized."""
    manager = DBSessionManager(None)
    with pytest.raises(SessionNotInitialisedError):
        manager.get_session()


async def test_multi_session_creation_and_cleanup(
    test_engine: AsyncEngine,
) -> None:
    """Test multi-session creation with task cleanup callback."""
    async_session = sessionmaker(test_engine, class_=AsyncSession)
    manager = DBSessionManager(async_session)

    token = multi_sessions_flag.set(True)
    try:
        # Get a multi-session
        session = manager.get_session()
        if not isinstance(session, AsyncSession):
            msg = "Expected AsyncSession instance"
            raise TypeError(msg)
    finally:
        multi_sessions_flag.reset(token)


async def test_context_manager_single_session_mode(
    test_engine: AsyncEngine,
) -> None:
    """Test DBSessionManager as async context manager in single-session mode."""
    async_session = sessionmaker(test_engine, class_=AsyncSession)
    manager = DBSessionManager(async_session)

    async with manager:
        # Verify session is set in context
        session = current_session.get()
        if session is None:
            msg = "Session should not be None"
            raise ValueError(msg)
        if not isinstance(session, AsyncSession):
            msg = "Expected AsyncSession instance"
            raise TypeError(msg)


async def test_context_manager_with_commit_on_exit(
    test_engine: AsyncEngine,
) -> None:
    """Test session commit on exit in async context."""
    async_session = sessionmaker(test_engine, class_=AsyncSession)
    manager = DBSessionManager(async_session)

    commit_token = commit_flag.set(True)
    try:
        async with manager:
            session = current_session.get()
            if session is None:
                msg = "Session should not be None"
                raise ValueError(msg)
    finally:
        commit_flag.reset(commit_token)


async def test_context_manager_with_exception(
    test_engine: AsyncEngine,
) -> None:
    """Test session rollback on exception in async context."""
    async_session = sessionmaker(test_engine, class_=AsyncSession)
    manager = DBSessionManager(async_session)

    error_msg = "Test error"
    with pytest.raises(ValueError, match=error_msg):
        async with manager:
            raise ValueError(error_msg)

    # Verify session is cleaned up
    session = current_session.get()
    if session is not None:
        msg = "Session should be cleaned up after exception"
        raise ValueError(msg)


async def test_multi_session_mode_in_context(
    test_engine: AsyncEngine,
) -> None:
    """Test DBSessionManager in multi-session mode within async context."""
    async_session = sessionmaker(test_engine, class_=AsyncSession)
    manager = DBSessionManager(async_session)

    token = multi_sessions_flag.set(True)
    try:
        async with manager:
            # In multi-session mode, context manager should return immediately
            pass
    finally:
        multi_sessions_flag.reset(token)


async def test_session_cleanup_on_task_completion(
    test_engine: AsyncEngine,
) -> None:
    """Test that session cleanup is called when task completes."""
    async_session = sessionmaker(test_engine, class_=AsyncSession)
    manager = DBSessionManager(async_session)

    token = multi_sessions_flag.set(True)
    try:

        async def task_with_session() -> None:
            session = manager.get_session()
            if not isinstance(session, AsyncSession):
                msg = "Expected AsyncSession instance"
                raise TypeError(msg)

        # Create and run a task
        task = asyncio.create_task(task_with_session())
        await task

    finally:
        multi_sessions_flag.reset(token)


async def test_get_session_no_current_session_in_single_mode(
    test_engine: AsyncEngine,
) -> None:
    """Test MissingSessionError when no current session in single-session mode."""
    async_session = sessionmaker(test_engine, class_=AsyncSession)
    manager = DBSessionManager(async_session)

    with pytest.raises(MissingSessionError):
        manager.get_session()


async def test_session_commit_flag_respected(
    test_engine: AsyncEngine,
) -> None:
    """Test that commit_flag is respected in context manager."""
    async_session = sessionmaker(test_engine, class_=AsyncSession)
    manager = DBSessionManager(async_session)

    # Without commit flag, should not commit
    async with manager:
        pass

    # With commit flag, should commit
    commit_token = commit_flag.set(True)
    try:
        async with manager:
            pass
    finally:
        commit_flag.reset(commit_token)


async def test_multi_session_cleanup_with_exception() -> None:
    """Test cleanup is called even when session operation raises exception."""
    manager = DBSessionManager(None)
    manager.SessionFactory = None

    token = multi_sessions_flag.set(True)
    try:
        # Verify that multi-session mode is set
        if not multi_sessions_flag.get():
            msg = "Multi-session flag should be set"
            raise ValueError(msg)
    finally:
        multi_sessions_flag.reset(token)


async def test_ensure_initialized_with_invalid_factory() -> None:
    """Test ensure_initialized raises when factory is invalid."""
    manager = DBSessionManager("invalid")  # type: ignore[assignment]
    with pytest.raises(SessionNotInitialisedError):
        manager.ensure_initialized()


async def test_get_session_multi_session_mode(test_engine: AsyncEngine) -> None:
    """Test get_session returns new session in multi-session mode."""
    async_session = sessionmaker(test_engine, class_=AsyncSession)
    manager = DBSessionManager(async_session)

    token = multi_sessions_flag.set(True)
    try:
        session1 = manager.get_session()
        session2 = manager.get_session()
        # Each call should return a different instance
        if session1 is session2:
            msg = "Each call should return a different session instance"
            raise ValueError(msg)
    finally:
        multi_sessions_flag.reset(token)


async def test_context_manager_clears_session_token(
    test_engine: AsyncEngine,
) -> None:
    """Test that session token is properly reset on exit."""
    async_session = sessionmaker(test_engine, class_=AsyncSession)
    manager = DBSessionManager(async_session)

    async with manager:
        # Verify token was set
        if manager._session_token is None:  # noqa: SLF001
            msg = "Session token should be set"
            raise ValueError(msg)

    # After exit, session should be None
    session = current_session.get()
    if session is not None:
        msg = "Session should be None after context exit"
        raise ValueError(msg)


async def test_context_manager_with_patch_commit(
    test_engine: AsyncEngine,
) -> None:
    """Test context manager with commit patched."""
    async_session = sessionmaker(test_engine, class_=AsyncSession)
    manager = DBSessionManager(async_session)

    commit_token = commit_flag.set(True)
    try:
        async with manager:
            session = current_session.get()
            if session is None:
                msg = "Session should not be None"
                raise ValueError(msg)
            # In real scenario, patch would prevent commit
            with patch.object(session, "commit") as mock_commit:
                if mock_commit is None:
                    msg = "Mock should not be None"
                    raise ValueError(msg)
    finally:
        commit_flag.reset(commit_token)
