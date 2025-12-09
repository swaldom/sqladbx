"""Tests for multiple database instances (master/replica setup)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from sqladbx import db
from sqladbx.exceptions import SessionNotInitialisedError
from sqladbx.proxy import DBProxy

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine


async def test_create_separate_db_instance(test_engine: AsyncEngine) -> None:
    """Test creating a separate database instance."""
    replica_db = DBProxy()

    # Both should be initialized independently
    db.initialize(test_engine)
    replica_db.initialize(test_engine)

    # Both should have their own managers
    if db.manager is None:
        msg = "db.manager should not be None"
        raise ValueError(msg)
    if replica_db.manager is None:
        msg = "replica_db.manager should not be None"
        raise ValueError(msg)

    if db.manager is replica_db.manager:
        msg = "db and replica_db should have different managers"
        raise ValueError(msg)


async def test_master_replica_session_access(test_engine: AsyncEngine) -> None:
    """Test accessing sessions from both master and replica."""
    master_db = db
    replica_db = DBProxy()

    # Initialize both
    master_db.initialize(test_engine)
    replica_db.initialize(test_engine)

    # Get sessions from master
    async with master_db():
        master_session = master_db.session
        if not isinstance(master_session, AsyncSession):
            msg = "Expected AsyncSession from master"
            raise TypeError(msg)

    # Get sessions from replica
    async with replica_db():
        replica_session = replica_db.session
        if not isinstance(replica_session, AsyncSession):
            msg = "Expected AsyncSession from replica"
            raise TypeError(msg)


async def test_master_replica_independent_sessions(
    test_engine: AsyncEngine,
) -> None:
    """Test that master and replica sessions are independent."""
    master_db = db
    replica_db = DBProxy()

    master_db.initialize(test_engine)
    replica_db.initialize(test_engine)

    # Get a session from each
    async with master_db():
        master_session = master_db.session
        master_session_id = id(master_session)

    async with replica_db():
        replica_session = replica_db.session
        replica_session_id = id(replica_session)

    # Sessions should be different instances
    if master_session_id == replica_session_id:
        msg = "Master and replica sessions should be different"
        raise ValueError(msg)


async def test_multi_session_on_master_and_replica(
    test_engine: AsyncEngine,
) -> None:
    """Test multi-session mode on both master and replica."""
    master_db = db
    replica_db = DBProxy()

    master_db.initialize(test_engine)
    replica_db.initialize(test_engine)

    # Multi-session on master
    async with master_db(multi_sessions=True):
        master_session_1 = master_db.session
        master_session_2 = master_db.session

        if master_session_1 is master_session_2:
            msg = "Multi-session should return different sessions"
            raise ValueError(msg)

    # Multi-session on replica
    async with replica_db(multi_sessions=True):
        replica_session_1 = replica_db.session
        replica_session_2 = replica_db.session

        if replica_session_1 is replica_session_2:
            msg = "Multi-session should return different sessions"
            raise ValueError(msg)


async def test_commit_on_exit_independent(test_engine: AsyncEngine) -> None:
    """Test that commit_on_exit works independently for each db."""
    master_db = db
    replica_db = DBProxy()

    master_db.initialize(test_engine)
    replica_db.initialize(test_engine)

    # Master with commit
    async with master_db(commit_on_exit=True):
        master_session = master_db.session
        if master_session is None:
            msg = "Master session should not be None"
            raise ValueError(msg)

    # Replica without commit
    async with replica_db(commit_on_exit=False):
        replica_session = replica_db.session
        if replica_session is None:
            msg = "Replica session should not be None"
            raise ValueError(msg)


async def test_uninitialized_replica_raises_error() -> None:
    """Test that uninitialized replica raises SessionNotInitialisedError."""
    replica_db = DBProxy()

    # Don't initialize replica_db - should raise when trying to use it
    with pytest.raises(SessionNotInitialisedError):
        async with replica_db():
            _ = replica_db.session
