"""Unit tests for engine module."""

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from sqladbx.engine import create_engine


def test_create_engine_with_url() -> None:
    """Test creating engine from database URL."""
    engine = create_engine("sqlite+aiosqlite:///:memory:")
    assert isinstance(engine, AsyncEngine)


def test_create_engine_with_custom_engine() -> None:
    """Test providing custom engine."""
    custom_engine = create_engine("sqlite+aiosqlite:///:memory:")
    engine = create_engine(None, custom_engine=custom_engine)
    assert engine is custom_engine


def test_create_engine_missing_url() -> None:
    """Test error when no URL or custom engine provided."""
    with pytest.raises(ValueError):
        create_engine(None)


def test_create_engine_with_args() -> None:
    """Test creating engine with additional arguments."""
    engine = create_engine(
        "sqlite+aiosqlite:///:memory:",
        engine_args={"echo": True, "pool_pre_ping": True},
    )
    assert isinstance(engine, AsyncEngine)
