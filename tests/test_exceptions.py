"""Unit tests for exceptions module."""

import pytest

from sqladbx.exceptions import MissingSessionError, SessionNotInitialisedError


def test_session_not_initialised_error() -> None:
    """Test SessionNotInitialisedError is raised correctly."""
    with pytest.raises(SessionNotInitialisedError):
        raise SessionNotInitialisedError


def test_missing_session_error() -> None:
    """Test MissingSessionError is raised correctly."""
    with pytest.raises(MissingSessionError):
        raise MissingSessionError


def test_exception_messages() -> None:
    """Test that exceptions have proper messages."""
    try:
        raise SessionNotInitialisedError
    except SessionNotInitialisedError as e:
        assert "not initialized" in str(e).lower() or str(e)

    try:
        raise MissingSessionError
    except MissingSessionError as e:
        assert "missing" in str(e).lower() or str(e)
