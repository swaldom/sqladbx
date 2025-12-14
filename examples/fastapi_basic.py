"""Basic FastAPI example with sqladbx.

This example demonstrates:
- Basic CRUD operations
- Direct session access without context manager
- Commit on exit functionality
- Error handling

Run: uv run fastapi dev examples/fastapi_basic.py
"""

from collections.abc import AsyncGenerator
from typing import Any

import sqlalchemy as sa
from fastapi import FastAPI, HTTPException, status
from fastapi.concurrency import asynccontextmanager
from pydantic import BaseModel, ConfigDict
from sqlalchemy import orm as sa_orm

from sqladbx import SQLAlchemyMiddleware, db

# Database setup
Base = sa_orm.declarative_base()


class User(Base):
    """User model."""

    __tablename__ = "users"

    id = sa.Column(sa.Integer, primary_key=True)
    name = sa.Column(sa.String(100), nullable=False)
    email = sa.Column(sa.String(100), unique=True, nullable=False)


class UserCreate(BaseModel):
    """User creation schema."""

    name: str
    email: str


class UserResponse(BaseModel):
    """User response schema."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    email: str


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:  # noqa: ARG001
    """Lifespan context to create tables on startup and dispose on shutdown."""
    async with db.engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    await db.dispose()


# FastAPI app
app = FastAPI(title="sqladbx Basic Example", lifespan=lifespan)

# Add middleware - engine is created inside
app.add_middleware(SQLAlchemyMiddleware, db_url="sqlite+aiosqlite:///./fastapi_basic.db")


@app.get("/users", response_model=list[UserResponse])
async def list_users() -> Any:
    """List all users."""
    return (await db.session.scalars(sa.select(User))).all()


@app.get("/users/{user_id}", response_model=UserResponse)
async def get_user(user_id: int) -> Any:
    """Get user by ID."""
    result = await db.session.execute(sa.select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user


@app.post("/users", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(user_data: UserCreate) -> Any:
    """Create a new user."""
    user = User(name=user_data.name, email=user_data.email)
    db.session.add(user)
    await db.session.commit()
    return user


@app.put("/users/{user_id}", response_model=UserResponse)
async def update_user(user_id: int, user_data: UserCreate) -> Any:
    """Update user."""
    result = await db.session.execute(sa.select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.name = user_data.name
    user.email = user_data.email
    await db.session.commit()
    return user


@app.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(user_id: int) -> None:
    """Delete user."""
    result = await db.session.execute(sa.select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    await db.session.delete(user)
    await db.session.commit()
