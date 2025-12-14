"""Integration tests for FastAPI."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
import sqlalchemy as sa
from fastapi import FastAPI, status
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel import Field, SQLModel

from sqladbx import SQLAlchemyMiddleware, db

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator


class User(SQLModel, table=True):
    """User model for testing."""

    id: int | None = Field(default=None, primary_key=True)
    name: str
    email: str


@pytest.fixture
async def fastapi_app() -> AsyncGenerator[FastAPI]:
    """Create FastAPI app with SQLAlchemy middleware."""
    # Initialize engine and create tables before middleware
    engine = create_async_engine("sqlite+aiosqlite:///./fastapi_test.db")
    # Create tables
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    app = FastAPI()

    # Add middleware with pre-initialized engine
    app.add_middleware(SQLAlchemyMiddleware, db_url="sqlite+aiosqlite:///./fastapi_test.db")

    @app.post("/users", status_code=status.HTTP_201_CREATED)
    async def create_user(name: str, email: str) -> Any:
        """Create a new user."""
        user = User(name=name, email=email)
        db.session.add(user)
        await db.session.commit()
        await db.session.refresh(user)
        return {"id": user.id, "name": user.name, "email": user.email}

    @app.get("/users")
    async def list_users() -> Any:
        """List all users."""
        result = await db.session.scalars(sa.select(User))
        users = result.all()
        return [{"id": u.id, "name": u.name, "email": u.email} for u in users]

    yield app

    # Cleanup
    await engine.dispose()
    await db.dispose()

    # Remove test database file
    test_db_path = Path("./fastapi_test.db")
    if test_db_path.exists():
        test_db_path.unlink()


@pytest.fixture
async def client(fastapi_app: FastAPI) -> AsyncGenerator[AsyncClient]:
    """Create AsyncClient for FastAPI app."""
    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_create_user_endpoint(client: AsyncClient) -> None:
    """Test creating a user via API."""
    response = await client.post("/users", params={"name": "John Doe", "email": "john@example.com"})

    assert response.status_code == status.HTTP_201_CREATED
    data = response.json()
    assert data["name"] == "John Doe"
    assert data["email"] == "john@example.com"
    assert data["id"] is not None


@pytest.mark.asyncio
async def test_list_users_endpoint(client: AsyncClient) -> None:
    """Test listing users via API."""
    # Create some users first
    await client.post("/users", params={"name": "Alice", "email": "alice@example.com"})
    await client.post("/users", params={"name": "Bob", "email": "bob@example.com"})

    # List users
    response = await client.get("/users")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    expected_items = 2
    assert len(data) == expected_items
    assert data[0]["name"] == "Alice"
    assert data[1]["name"] == "Bob"


@pytest.mark.asyncio
async def test_create_and_list_users(client: AsyncClient) -> None:
    """Test creating and listing users in sequence."""
    # Initially empty
    response = await client.get("/users")
    assert response.status_code == status.HTTP_200_OK
    assert len(response.json()) == 0

    # Create first user
    response = await client.post("/users", params={"name": "User1", "email": "user1@test.com"})
    assert response.status_code == status.HTTP_201_CREATED
    user1_id = response.json()["id"]

    # Check list has 1 user
    response = await client.get("/users")
    assert len(response.json()) == 1

    # Create second user
    response = await client.post("/users", params={"name": "User2", "email": "user2@test.com"})
    assert response.status_code == status.HTTP_201_CREATED
    user2_id = response.json()["id"]

    # Check list has 2 users
    response = await client.get("/users")
    users = response.json()
    expected_items = 2
    assert len(users) == expected_items
    assert users[0]["id"] == user1_id
    assert users[1]["id"] == user2_id
