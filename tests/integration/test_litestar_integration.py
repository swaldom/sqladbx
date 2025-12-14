"""Integration tests for Litestar."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
import sqlalchemy as sa
from httpx import ASGITransport, AsyncClient
from litestar import Litestar, get, post, status_codes
from litestar.middleware import DefineMiddleware
from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel import Field, SQLModel

from sqladbx import SQLAlchemyMiddleware, db

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator


class Product(SQLModel, table=True):
    """Product model for testing."""

    id: int | None = Field(default=None, primary_key=True)
    name: str
    price: float


@pytest.fixture
async def litestar_app() -> AsyncGenerator[Litestar]:
    """Create Litestar app with SQLAlchemy integration."""
    # Initialize engine and create tables
    engine = create_async_engine("sqlite+aiosqlite:///./test_litestar.db")
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    @post("/products", status_code=status_codes.HTTP_201_CREATED)
    async def create_product(name: str, price: float) -> dict[str, Any]:
        """Create a new product."""
        product = Product(name=name, price=price)
        db.session.add(product)
        await db.session.commit()
        await db.session.refresh(product)
        return {"id": product.id, "name": product.name, "price": product.price}

    @get("/products")
    async def list_products() -> list[dict[str, Any]]:
        """List all products."""
        result = await db.session.scalars(sa.select(Product))
        products = result.all()
        return [{"id": p.id, "name": p.name, "price": p.price} for p in products]

    app = Litestar(
        route_handlers=[create_product, list_products],
        middleware=[DefineMiddleware(SQLAlchemyMiddleware, db_url="sqlite+aiosqlite:///./test_litestar.db")],
    )

    yield app

    # Cleanup
    await engine.dispose()
    await db.dispose()

    # Remove test database file
    test_db_path = Path("./test_litestar.db")
    if test_db_path.exists():
        test_db_path.unlink()


@pytest.fixture
async def client(litestar_app: Litestar) -> AsyncGenerator[AsyncClient]:
    """Create AsyncClient for Litestar app."""
    async with AsyncClient(transport=ASGITransport(app=litestar_app), base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_create_product_endpoint(client: AsyncClient) -> None:
    """Test creating a product via API."""
    price = 999.99
    response = await client.post("/products", params={"name": "Laptop", "price": 999.99})

    assert response.status_code == status_codes.HTTP_201_CREATED
    data = response.json()
    assert data["name"] == "Laptop"
    assert data["price"] == price
    assert data["id"] is not None


@pytest.mark.asyncio
async def test_list_products_endpoint(client: AsyncClient) -> None:
    """Test listing products via API."""
    # Create some products first
    await client.post("/products", params={"name": "Mouse", "price": 29.99})
    await client.post("/products", params={"name": "Keyboard", "price": 79.99})

    # List products
    response = await client.get("/products")

    assert response.status_code == status_codes.HTTP_200_OK
    data = response.json()
    expected_items = 2
    assert len(data) == expected_items
    assert data[0]["name"] == "Mouse"
    assert data[1]["name"] == "Keyboard"


@pytest.mark.asyncio
async def test_create_and_list_products(client: AsyncClient) -> None:
    """Test creating and listing products in sequence."""
    # Initially empty
    response = await client.get("/products")
    assert response.status_code == status_codes.HTTP_200_OK
    assert len(response.json()) == 0

    # Create first product
    response = await client.post("/products", params={"name": "Monitor", "price": 299.99})
    assert response.status_code == status_codes.HTTP_201_CREATED
    product1_id = response.json()["id"]

    # Check list has 1 product
    response = await client.get("/products")
    assert len(response.json()) == 1

    # Create second product
    response = await client.post("/products", params={"name": "Headphones", "price": 149.99})
    assert response.status_code == status_codes.HTTP_201_CREATED
    product2_id = response.json()["id"]

    # Check list has 2 products
    response = await client.get("/products")
    products = response.json()
    expected_items = 2
    assert len(products) == expected_items
    assert products[0]["id"] == product1_id
    assert products[1]["id"] == product2_id
