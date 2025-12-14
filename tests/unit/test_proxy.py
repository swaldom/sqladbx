"""Unit tests for sqladbx.proxy module.

Tests DBProxy, SingleContext, and MultiContext classes.
"""

import warnings

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine

from sqladbx.exceptions import SessionNotInitializedError
from sqladbx.proxy import DBProxy, MultiContext, SingleContext


def test_init_creates_empty_proxy() -> None:
    """Test DBProxy initializes with None values."""
    proxy = DBProxy()
    assert proxy.session_factory is None
    assert proxy.manager is None
    assert proxy.engine is None


def test_initialize_with_engine() -> None:
    """Test initialize with pre-configured engine."""
    proxy = DBProxy()
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")

    proxy.initialize(engine)

    assert proxy.engine is engine
    assert proxy.session_factory is not None
    assert proxy.manager is not None


def test_initialize_with_db_url() -> None:
    """Test initialize with db_url."""
    proxy = DBProxy()

    proxy.initialize(db_url="sqlite+aiosqlite:///:memory:")

    assert proxy.engine is not None
    assert proxy.session_factory is not None
    assert proxy.manager is not None


def test_initialize_with_engine_args() -> None:
    """Test initialize with engine_args."""
    proxy = DBProxy()

    proxy.initialize(
        db_url="sqlite+aiosqlite:///:memory:",
        engine_args={"echo": True},
    )

    assert proxy.engine is not None
    assert proxy.engine.echo is True


def test_initialize_with_session_args() -> None:
    """Test initialize with session_args."""
    proxy = DBProxy()

    proxy.initialize(
        db_url="sqlite+aiosqlite:///:memory:",
        session_args={"expire_on_commit": True},
    )

    assert proxy.session_factory is not None


def test_initialize_without_engine_or_url_raises() -> None:
    """Test initialize raises without engine or db_url."""
    proxy = DBProxy()

    with pytest.raises(ValueError, match="Either engine or db_url must be provided"):
        proxy.initialize()


def test_session_not_initialized_raises() -> None:
    """Test session property raises when not initialized."""
    proxy = DBProxy()

    with pytest.raises(SessionNotInitializedError):
        _ = proxy.session


async def test_session_returns_async_session() -> None:
    """Test session property returns AsyncSession."""
    proxy = DBProxy()
    proxy.initialize(db_url="sqlite+aiosqlite:///:memory:")

    async with proxy():
        session = proxy.session
        assert isinstance(session, AsyncSession)


def test_engine_before_initialize_is_none() -> None:
    """Test engine is None before initialize."""
    proxy = DBProxy()
    assert proxy.engine is None


def test_engine_after_initialize_is_set() -> None:
    """Test engine is set after initialize."""
    proxy = DBProxy()
    proxy.initialize(db_url="sqlite+aiosqlite:///:memory:")

    assert proxy.engine is not None
    assert isinstance(proxy.engine, AsyncEngine)


def test_call_not_initialized_raises() -> None:
    """Test __call__ raises when not initialized."""
    proxy = DBProxy()

    with pytest.raises(SessionNotInitializedError):
        proxy()


def test_call_returns_single_context() -> None:
    """Test __call__ returns SingleContext by default."""
    proxy = DBProxy()
    proxy.initialize(db_url="sqlite+aiosqlite:///:memory:")

    context = proxy()
    assert isinstance(context, SingleContext)


def test_call_returns_multi_context() -> None:
    """Test __call__ returns MultiContext with multi_sessions=True."""
    proxy = DBProxy()
    proxy.initialize(db_url="sqlite+aiosqlite:///:memory:")

    context = proxy(multi_sessions=True)
    assert isinstance(context, MultiContext)


def test_call_with_commit_on_exit() -> None:
    """Test __call__ with commit_on_exit parameter."""
    proxy = DBProxy()
    proxy.initialize(db_url="sqlite+aiosqlite:///:memory:")

    context = proxy(commit_on_exit=True)
    assert isinstance(context, SingleContext)


def test_call_with_session_args() -> None:
    """Test __call__ with session_args parameter."""
    proxy = DBProxy()
    proxy.initialize(db_url="sqlite+aiosqlite:///:memory:")

    context = proxy(session_args={"expire_on_commit": True})
    assert isinstance(context, SingleContext)


class TestDBProxyDispose:
    """Tests for DBProxy.dispose() method."""

    async def test_dispose_cleans_up_resources(self) -> None:
        """Test dispose cleans up all resources."""
        proxy = DBProxy()
        proxy.initialize(db_url="sqlite+aiosqlite:///:memory:")

        assert proxy.engine is not None
        assert proxy.session_factory is not None

        await proxy.dispose()

        assert proxy.engine is None
        assert proxy.session_factory is None
        assert proxy.manager is None

    async def test_dispose_multiple_times_safe(self) -> None:
        """Test dispose can be called multiple times safely."""
        proxy = DBProxy()
        proxy.initialize(db_url="sqlite+aiosqlite:///:memory:")

        await proxy.dispose()
        await proxy.dispose()  # Should not raise

    async def test_dispose_without_initialize_safe(self) -> None:
        """Test dispose without initialize is safe."""
        proxy = DBProxy()
        await proxy.dispose()  # Should not raise


async def test_single_context_aenter() -> None:
    """Test SingleContext __aenter__ returns manager."""
    proxy = DBProxy()
    proxy.initialize(db_url="sqlite+aiosqlite:///:memory:")

    context = proxy()
    result = await context.__aenter__()

    assert result is proxy.manager

    await context.__aexit__(None, None, None)


# rm after impl integration tests
async def test_single_context_aexit_resets_context_vars() -> None:
    """Test SingleContext __aexit__ resets ContextVars."""
    proxy = DBProxy()
    proxy.initialize(db_url="sqlite+aiosqlite:///:memory:")

    async with proxy():
        pass

    # ContextVars should be reset (tested in functional tests)


async def test_multi_context_aenter() -> None:
    """Test MultiContext __aenter__ returns manager."""
    proxy = DBProxy()
    proxy.initialize(db_url="sqlite+aiosqlite:///:memory:")

    context = proxy(multi_sessions=True)
    result = await context.__aenter__()

    assert result is proxy.manager

    await context.__aexit__(None, None, None)


# rm after impl integration tests
async def test_multi_context_aexit_cleans_tracked_sessions() -> None:
    """Test MultiContext __aexit__ cleans up tracked sessions."""
    proxy = DBProxy()
    proxy.initialize(db_url="sqlite+aiosqlite:///:memory:")

    async with proxy(multi_sessions=True):
        # Create some sessions
        _ = proxy.session
        _ = proxy.session

    # Sessions should be cleaned up (tested in functional tests)


# rm after impl integration tests
async def test_multi_context_with_exception_rollback() -> None:
    """Test MultiContext rolls back on exception."""
    proxy = DBProxy()
    proxy.initialize(db_url="sqlite+aiosqlite:///:memory:")

    try:
        async with proxy(multi_sessions=True):
            _ = proxy.session
            raise ValueError("Test error")  # noqa: TRY301, TRY003, EM101
    except ValueError:
        pass  # Expected

    # Rollback should have been called


# rm after impl integration tests
async def test_multi_context_cleanup_with_mock_error() -> None:
    """Test MultiContext handles cleanup errors (via mock)."""
    proxy = DBProxy()
    proxy.initialize(db_url="sqlite+aiosqlite:///:memory:")

    with warnings.catch_warnings(record=True):
        warnings.simplefilter("always")

        async with proxy(multi_sessions=True, commit_on_exit=True):
            # Create a session
            session = proxy.session

            # Replace commit with a mock that raises
            async def failing_commit() -> None:
                raise Exception("Mock commit error")  # noqa: TRY002, TRY003, EM101

            session.commit = failing_commit
