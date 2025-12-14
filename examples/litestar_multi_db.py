"""Multi-database Litestar example with sqladbx and class-based controllers.

This example demonstrates:
- Multiple database setup
- SQLModel integration with sqladbx
- Class-based controllers for better organization
- Creating custom database middleware
- Proper database lifecycle management

Run: uv run litestar --app=examples.litestar_multi_db:app run --reload
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any, ClassVar

from litestar import Controller, Litestar, delete, get, post, put
from litestar.exceptions import NotFoundException
from litestar.middleware import DefineMiddleware
from litestar.status_codes import HTTP_201_CREATED, HTTP_204_NO_CONTENT
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
    is_active: bool = Field(default=True)


class Product(SQLModel, table=True):
    """Product model - stored in second database."""

    __tablename__ = "products"

    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(max_length=200)
    price: float
    stock: int = Field(default=0)
    category: str = Field(max_length=100)


class UserCreate(SQLModel):
    """User creation schema."""

    name: str
    email: str
    is_active: bool = True


class ProductCreate(SQLModel):
    """Product creation schema."""

    name: str
    price: float
    stock: int = 0
    category: str


# ============================================================================
# Database Setup
# ============================================================================

# Create separate database instances
FirstDBMiddleware, first_db = create_middleware_and_db()
SecondDBMiddleware, second_db = create_middleware_and_db()


@asynccontextmanager
async def lifespan(app: Litestar) -> AsyncGenerator[None]:  # noqa: ARG001
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
# Controllers
# ============================================================================


class UserController(Controller):
    """User management controller - uses first database."""

    path = "/users"
    tags: ClassVar[list[str]] = ["users"]

    @get()
    async def list_users(self, is_active: bool | None = None) -> list[User]:
        """List all users with optional filter."""
        query = select(User)
        if is_active is not None:
            query = query.where(User.is_active == is_active)

        result = await first_db.session.scalars(query)
        return result.all()

    @get("/{user_id:int}")
    async def get_user(self, user_id: int) -> User:
        """Get user by ID."""
        user = await first_db.session.get(User, user_id)
        if not user:
            raise NotFoundException(detail="User not found")
        return user

    @post(status_code=HTTP_201_CREATED)
    async def create_user(self, data: UserCreate) -> User:
        """Create a new user."""
        user = User.model_validate(data)
        first_db.session.add(user)
        await first_db.session.commit()
        await first_db.session.refresh(user)
        return user

    @put("/{user_id:int}")
    async def update_user(self, user_id: int, data: UserCreate) -> User:
        """Update user."""
        user = await first_db.session.get(User, user_id)
        if not user:
            raise NotFoundException(detail="User not found")

        user.name = data.name
        user.email = data.email
        user.is_active = data.is_active
        await first_db.session.commit()
        await first_db.session.refresh(user)
        return user

    @delete("/{user_id:int}", status_code=HTTP_204_NO_CONTENT)
    async def delete_user(self, user_id: int) -> None:
        """Delete user (soft delete by setting is_active=False)."""
        user = await first_db.session.get(User, user_id)
        if not user:
            raise NotFoundException(detail="User not found")

        user.is_active = False
        await first_db.session.commit()


class ProductController(Controller):
    """Product catalog controller - uses second database."""

    path = "/products"
    tags: ClassVar[list[str]] = ["products"]

    @get()
    async def list_products(
        self,
        category: str | None = None,
        min_stock: int | None = None,
        max_price: float | None = None,
    ) -> list[Product]:
        """List products with optional filters."""
        query = select(Product)

        if category:
            query = query.where(Product.category == category)
        if min_stock is not None:
            query = query.where(Product.stock >= min_stock)
        if max_price is not None:
            query = query.where(Product.price <= max_price)

        result = await second_db.session.scalars(query)
        return result.all()

    @get("/{product_id:int}")
    async def get_product(self, product_id: int) -> Product:
        """Get product by ID."""
        product = await second_db.session.get(Product, product_id)
        if not product:
            raise NotFoundException(detail="Product not found")
        return product

    @post(status_code=HTTP_201_CREATED)
    async def create_product(self, data: ProductCreate) -> Product:
        """Create a new product."""
        async with second_db(commit_on_exit=True):
            product = Product.model_validate(data)
            second_db.session.add(product)
            await second_db.session.flush()
            await second_db.session.refresh(product)
            return product

    @put("/{product_id:int}")
    async def update_product(self, product_id: int, data: ProductCreate) -> Product:
        """Update product."""
        async with second_db(commit_on_exit=True):
            product = await second_db.session.get(Product, product_id)
            if not product:
                raise NotFoundException(detail="Product not found")

            product.name = data.name
            product.price = data.price
            product.stock = data.stock
            product.category = data.category
            await second_db.session.flush()
            await second_db.session.refresh(product)
            return product

    @delete("/{product_id:int}", status_code=HTTP_204_NO_CONTENT)
    async def delete_product(self, product_id: int) -> None:
        """Delete product."""
        async with second_db(commit_on_exit=True):
            product = await second_db.session.get(Product, product_id)
            if not product:
                raise NotFoundException(detail="Product not found")

            await second_db.session.delete(product)


class AnalyticsController(Controller):
    """Analytics controller - queries both databases."""

    path = "/analytics"
    tags: ClassVar[list[str]] = ["analytics"]

    @get("/summary")
    async def get_summary(self) -> dict[str, Any]:
        """Get summary statistics from both databases."""
        # Get user stats from first database
        user_result = await first_db.session.scalars(select(User))
        users = user_result.all()
        active_users = sum(1 for u in users if u.is_active)

        # Get product stats from second database
        product_result = await second_db.session.scalars(select(Product))
        products = product_result.all()

        # Calculate category breakdown
        categories: dict[str, int] = {}
        total_stock = 0
        total_value = 0.0

        for product in products:
            categories[product.category] = categories.get(product.category, 0) + 1
            total_stock += product.stock
            total_value += product.price * product.stock

        return {
            "users": {
                "total": len(users),
                "active": active_users,
                "inactive": len(users) - active_users,
                "database": "first",
            },
            "products": {
                "total": len(products),
                "categories": categories,
                "total_stock": total_stock,
                "total_value": round(total_value, 2),
                "database": "second",
            },
        }

    @get("/categories")
    async def get_categories(self) -> dict[str, Any]:
        """Get product breakdown by category."""
        product_result = await second_db.session.scalars(select(Product))
        products = product_result.all()

        categories: dict[str, dict[str, Any]] = {}
        for product in products:
            if product.category not in categories:
                categories[product.category] = {
                    "count": 0,
                    "total_stock": 0,
                    "total_value": 0.0,
                    "avg_price": 0.0,
                }

            cat = categories[product.category]
            cat["count"] += 1
            cat["total_stock"] += product.stock
            cat["total_value"] += product.price * product.stock

        # Calculate averages
        for cat_data in categories.values():
            if cat_data["count"] > 0:
                cat_data["avg_price"] = round(cat_data["total_value"] / cat_data["count"], 2)
            cat_data["total_value"] = round(cat_data["total_value"], 2)

        return {"categories": categories}


# ============================================================================
# Application
# ============================================================================

app = Litestar(
    route_handlers=[
        UserController,
        ProductController,
        AnalyticsController,
    ],
    middleware=[
        # First database middleware
        DefineMiddleware(
            FirstDBMiddleware,
            db_proxy=first_db,
            db_url="sqlite+aiosqlite:///./litestar_multi_first.db",
            commit_on_exit=True,
        ),
        # Second database middleware
        DefineMiddleware(
            SecondDBMiddleware,
            db_proxy=second_db,
            db_url="sqlite+aiosqlite:///./litestar_multi_second.db",
        ),
    ],
    lifespan=[lifespan],
)
