"""Multi-database FastAPI example with sqladbx and SQLModel.

This example demonstrates:
- Multiple database setup
- SQLModel integration with sqladbx
- Creating custom database middleware
- Proper database lifecycle management

Run: uv run fastapi dev examples/fastapi_multi_db.py
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, status
from sqlmodel import Field, SQLModel, select

from sqladbx import create_middleware_and_db

# ============================================================================
# Models
# ============================================================================


class User(SQLModel, table=True):
    """User model - stored in first database."""

    __tablename__ = "users"

    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(max_length=100)
    email: str = Field(max_length=100, unique=True)


class Product(SQLModel, table=True):
    """Product model - stored in second database."""

    __tablename__ = "products"

    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(max_length=200)
    price: float
    stock: int = Field(default=0)


class UserCreate(SQLModel):
    """User creation schema."""

    name: str
    email: str


class ProductCreate(SQLModel):
    """Product creation schema."""

    name: str
    price: float
    stock: int = 0


# ============================================================================
# Database Setup
# ============================================================================

# Create separate database instances
FirstDBMiddleware, first_db = create_middleware_and_db()
SecondDBMiddleware, second_db = create_middleware_and_db()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:  # noqa: ARG001
    """Lifespan context to create tables and dispose engines."""
    # Create tables in first database
    async with first_db.engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    # Create tables in second database
    async with second_db.engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    yield

    # Dispose both engines
    await first_db.dispose()
    await second_db.dispose()


# ============================================================================
# FastAPI App
# ============================================================================

app = FastAPI(title="sqladbx Multi-Database Example", lifespan=lifespan)

# Add middleware for first database
app.add_middleware(
    FirstDBMiddleware,
    db_url="sqlite+aiosqlite:///./fastapi_first.db",
    commit_on_exit=True,
)

# Add middleware for second database
app.add_middleware(
    SecondDBMiddleware,
    db_url="sqlite+aiosqlite:///./fastapi_second.db",
)


# ============================================================================
# User Endpoints (First Database)
# ============================================================================


@app.get("/users", response_model=list[User], tags=["Users"])
async def list_users() -> Any:
    """List all users from first database."""
    result = await first_db.session.scalars(select(User))
    return result.all()


@app.get("/users/{user_id}", response_model=User, tags=["Users"])
async def get_user(user_id: int) -> Any:
    """Get user by ID from first database."""
    user = await first_db.session.get(User, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    return user


@app.post(
    "/users",
    response_model=User,
    status_code=status.HTTP_201_CREATED,
    tags=["Users"],
)
async def create_user(user_data: UserCreate) -> Any:
    """Create a new user in first database."""
    user = User.model_validate(user_data)
    first_db.session.add(user)
    await first_db.session.flush()
    await first_db.session.refresh(user)
    return user


@app.put("/users/{user_id}", response_model=User, tags=["Users"])
async def update_user(user_id: int, user_data: UserCreate) -> Any:
    """Update user in first database."""
    user = await first_db.session.get(User, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    user.name = user_data.name
    user.email = user_data.email
    await first_db.session.flush()
    await first_db.session.refresh(user)
    return user


@app.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["Users"])
async def delete_user(user_id: int) -> None:
    """Delete user from first database."""
    user = await first_db.session.get(User, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    await first_db.session.delete(user)


# ============================================================================
# Product Endpoints (Second Database)
# ============================================================================


@app.get("/products", response_model=list[Product], tags=["Products"])
async def list_products(
    min_stock: int | None = None,
    max_price: float | None = None,
) -> Any:
    """List products from second database with optional filters."""
    query = select(Product)

    if min_stock is not None:
        query = query.where(Product.stock >= min_stock)
    if max_price is not None:
        query = query.where(Product.price <= max_price)

    result = await second_db.session.scalars(query)
    return result.all()


@app.get("/products/{product_id}", response_model=Product, tags=["Products"])
async def get_product(product_id: int) -> Any:
    """Get product by ID from second database."""
    product = await second_db.session.get(Product, product_id)
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found",
        )
    return product


@app.post(
    "/products",
    response_model=Product,
    status_code=status.HTTP_201_CREATED,
    tags=["Products"],
)
async def create_product(product_data: ProductCreate) -> Any:
    """Create a new product in second database."""
    async with second_db(commit_on_exit=True):
        product = Product.model_validate(product_data)
        second_db.session.add(product)
        await second_db.session.flush()
        await second_db.session.refresh(product)
        return product


@app.put("/products/{product_id}", response_model=Product, tags=["Products"])
async def update_product(product_id: int, product_data: ProductCreate) -> Any:
    """Update product in second database."""
    async with second_db(commit_on_exit=True):
        product = await second_db.session.get(Product, product_id)
        if not product:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Product not found",
            )

        product.name = product_data.name
        product.price = product_data.price
        product.stock = product_data.stock
        await second_db.session.flush()
        await second_db.session.refresh(product)
        return product


@app.delete(
    "/products/{product_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["Products"],
)
async def delete_product(product_id: int) -> None:
    """Delete product from second database."""
    async with second_db(commit_on_exit=True):
        product = await second_db.session.get(Product, product_id)
        if not product:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Product not found",
            )

        await second_db.session.delete(product)


# ============================================================================
# Analytics Endpoints (Cross-Database)
# ============================================================================


@app.get("/analytics/summary", tags=["Analytics"])
async def get_summary() -> dict[str, Any]:
    """Get summary from both databases."""
    # Get user count from first database
    user_result = await first_db.session.scalars(select(User))
    user_count = len(user_result.all())

    # Get product stats from second database
    product_result = await second_db.session.scalars(select(Product))
    products = product_result.all()
    product_count = len(products)
    total_stock = sum(p.stock for p in products)
    avg_price = sum(p.price for p in products) / product_count if product_count > 0 else 0

    return {
        "users": {
            "total": user_count,
            "database": "first",
        },
        "products": {
            "total": product_count,
            "total_stock": total_stock,
            "average_price": round(avg_price, 2),
            "database": "second",
        },
    }
