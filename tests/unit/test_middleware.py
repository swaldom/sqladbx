"""Unit tests for sqladbx.middleware module.

Tests SQLAlchemyMiddleware and create_db_middleware factory.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import create_async_engine
from starlette.applications import Starlette

from sqladbx import DBProxy
from sqladbx.middleware import SQLAlchemyMiddleware, create_db_middleware


def test_init_with_db_url() -> None:
    """Test middleware can be initialized with db_url."""
    app = Starlette()

    # Should not raise
    middleware = SQLAlchemyMiddleware(
        app,
        db_url="sqlite+aiosqlite:///:memory:",
    )

    assert middleware.db_proxy is not None


def test_init_with_custom_engine() -> None:
    """Test middleware can be initialized with custom_engine."""
    app = Starlette()
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")

    middleware = SQLAlchemyMiddleware(
        app,
        custom_engine=engine,
    )

    assert middleware.db_proxy is not None


def test_init_without_url_or_engine_raises() -> None:
    """Test middleware raises without db_url or custom_engine."""
    app = Starlette()

    with pytest.raises(ValueError, match="Either db_url or custom_engine must be provided"):
        SQLAlchemyMiddleware(app)


def test_init_with_db_proxy() -> None:
    """Test middleware can use custom db_proxy."""
    app = Starlette()
    custom_db = DBProxy()

    middleware = SQLAlchemyMiddleware(
        app,
        db_url="sqlite+aiosqlite:///:memory:",
        db_proxy=custom_db,
    )

    assert middleware.db_proxy is custom_db


def test_create_db_middleware_returns_class() -> None:
    """Test create_db_middleware returns a class."""
    MiddlewareClass = create_db_middleware()

    assert isinstance(MiddlewareClass, type)
    assert issubclass(MiddlewareClass, SQLAlchemyMiddleware)


def test_create_db_middleware_with_db_proxy() -> None:
    """Test create_db_middleware with pre-bound db_proxy."""
    custom_db = DBProxy()
    MiddlewareClass = create_db_middleware(custom_db)

    assert isinstance(MiddlewareClass, type)
    assert issubclass(MiddlewareClass, SQLAlchemyMiddleware)


def test_create_db_middleware_creates_unique_classes() -> None:
    """Test create_db_middleware creates unique classes."""
    Middleware1 = create_db_middleware()
    Middleware2 = create_db_middleware()

    assert Middleware1 is not Middleware2

    # But both should be subclasses of SQLAlchemyMiddleware
    assert issubclass(Middleware1, SQLAlchemyMiddleware)
    assert issubclass(Middleware2, SQLAlchemyMiddleware)


def test_middleware_with_pre_bound_db_proxy() -> None:
    """Test middleware uses pre-bound db_proxy."""
    custom_db = DBProxy()
    MiddlewareClass = create_db_middleware(custom_db)

    app = Starlette()
    middleware = MiddlewareClass(
        app,
        db_url="sqlite+aiosqlite:///:memory:",
    )

    assert middleware.db_proxy is custom_db


@pytest.mark.asyncio
async def test_dispatch_wraps_request_in_db_context() -> None:
    """Test dispatch() wraps request handling in db context."""
    app = Starlette()
    middleware = SQLAlchemyMiddleware(
        app,
        db_url="sqlite+aiosqlite:///:memory:",
    )

    # Create mock request and response
    mock_request = MagicMock()
    mock_response = MagicMock()
    mock_call_next = AsyncMock(return_value=mock_response)

    # Call dispatch directly
    result = await middleware.dispatch(mock_request, mock_call_next)

    # Verify call_next was called with request
    mock_call_next.assert_called_once_with(mock_request)
    # Verify response was returned
    assert result is mock_response
