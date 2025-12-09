"""Advanced integration tests for middleware and session management."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from sqladbx import SQLAlchemyMiddleware

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine

HTTP_200 = 200
TEST_ERROR_MSG = "Test error"


@pytest.fixture
def starlette_app(test_engine: AsyncEngine) -> Starlette:
    """Create Starlette app with SQLAlchemy middleware."""

    async def test_route(request: object) -> JSONResponse:  # noqa: ARG001
        """Test route that uses db session."""
        return JSONResponse({"status": "ok"})

    async def commit_test(request: object) -> JSONResponse:  # noqa: ARG001
        """Test route with commit on exit."""
        return JSONResponse({"committed": True})

    routes = [
        Route("/test", endpoint=test_route),
        Route("/commit-test", endpoint=commit_test),
    ]
    app = Starlette(routes=routes)

    app.add_middleware(SQLAlchemyMiddleware, custom_engine=test_engine)

    return app


def test_middleware_dispatch_with_request(starlette_app: Starlette) -> None:
    """Test middleware dispatch with actual request."""
    client = TestClient(starlette_app)
    response = client.get("/test")
    assert response.status_code == HTTP_200  # noqa: S101
    assert response.json() == {"status": "ok"}  # noqa: S101


def test_middleware_with_commit_on_exit(test_engine: AsyncEngine) -> None:
    """Test middleware with commit_on_exit=True."""

    async def home(request: object) -> JSONResponse:  # noqa: ARG001
        return JSONResponse({"ok": True})

    routes = [
        Route("/", endpoint=home),
    ]

    app = Starlette(routes=routes)
    app.add_middleware(SQLAlchemyMiddleware, custom_engine=test_engine, commit_on_exit=True)

    client = TestClient(app)
    response = client.get("/")
    assert response.status_code == HTTP_200  # noqa: S101


def test_middleware_error_propagation(test_engine: AsyncEngine) -> None:
    """Test that middleware propagates errors correctly."""

    async def error_route(request: object) -> JSONResponse:  # noqa: ARG001
        msg = TEST_ERROR_MSG
        raise ValueError(msg)

    routes = [
        Route("/error", endpoint=error_route),
    ]
    app = Starlette(routes=routes)
    app.add_middleware(SQLAlchemyMiddleware, custom_engine=test_engine)

    client = TestClient(app)
    with pytest.raises(ValueError, match=TEST_ERROR_MSG):
        client.get("/error")
