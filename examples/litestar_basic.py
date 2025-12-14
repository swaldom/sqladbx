"""Basic Litestar example with sqladbx.

This example demonstrates:
- Basic CRUD operations with function-based endpoints
- Direct session access without context manager
- Commit on exit functionality
- Error handling with Litestar exceptions

Run: uv run litestar --app=examples.litestar_basic:app run --reload
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from litestar import Litestar, delete, get, post, put
from litestar.exceptions import NotFoundException
from litestar.middleware import DefineMiddleware
from litestar.status_codes import HTTP_201_CREATED, HTTP_204_NO_CONTENT
from sqlmodel import Field, SQLModel, select

from sqladbx import SQLAlchemyMiddleware, db

# ============================================================================
# Models
# ============================================================================


class User(SQLModel, table=True):
    """User model."""

    __tablename__ = "users"

    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(max_length=100)
    email: str = Field(max_length=100, unique=True)


class UserCreate(SQLModel):
    """User creation schema."""

    name: str
    email: str


class UserResponse(SQLModel):
    """User response schema."""

    id: int
    name: str
    email: str


# ============================================================================
# Lifespan
# ============================================================================


@asynccontextmanager
async def lifespan(app: Litestar) -> AsyncGenerator[None]:  # noqa: ARG001
    """Lifespan context to create tables on startup and dispose on shutdown."""
    async with db.engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    yield
    await db.dispose()


# ============================================================================
# Endpoints
# ============================================================================


@get("/users", tags=["users"])
async def list_users() -> list[User]:
    """List all users."""
    result = await db.session.scalars(select(User))
    return result.all()


@get("/users/{user_id:int}", tags=["users"])
async def get_user(user_id: int) -> User:
    """Get user by ID."""
    user = await db.session.get(User, user_id)
    if not user:
        raise NotFoundException(detail="User not found")
    return user


@post("/users", status_code=HTTP_201_CREATED, tags=["users"])
async def create_user(data: UserCreate) -> User:
    """Create a new user."""
    user = User.model_validate(data)
    db.session.add(user)
    await db.session.commit()
    await db.session.refresh(user)
    return user


@put("/users/{user_id:int}", tags=["users"])
async def update_user(user_id: int, data: UserCreate) -> User:
    """Update user."""
    user = await db.session.get(User, user_id)
    if not user:
        raise NotFoundException(detail="User not found")

    user.name = data.name
    user.email = data.email
    await db.session.commit()
    await db.session.refresh(user)
    return user


@delete("/users/{user_id:int}", status_code=HTTP_204_NO_CONTENT, tags=["users"])
async def delete_user(user_id: int) -> None:
    """Delete user."""
    user = await db.session.get(User, user_id)
    if not user:
        raise NotFoundException(detail="User not found")

    await db.session.delete(user)
    await db.session.commit()


# ============================================================================
# Application
# ============================================================================

app = Litestar(
    route_handlers=[
        list_users,
        get_user,
        create_user,
        update_user,
        delete_user,
    ],
    middleware=[
        DefineMiddleware(
            SQLAlchemyMiddleware,
            db_url="sqlite+aiosqlite:///./litestar_basic.db",
        ),
    ],
    lifespan=[lifespan],
)
