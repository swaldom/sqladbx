"""Unit tests for exceptions module."""

import pytest

from sqladbx.exceptions import MissingSessionError, SessionNotInitializedError


def test_session_not_initialized_error() -> None:
    """Test SessionNotInitializedError is raised correctly."""
    with pytest.raises(SessionNotInitializedError) as exc_info:
        raise SessionNotInitializedError
    assert "not initialized" in str(exc_info.value).lower()


def test_missing_session_error() -> None:
    """Test MissingSessionError is raised correctly."""
    with pytest.raises(MissingSessionError) as exc_info:
        raise MissingSessionError
    assert "no session found" in str(exc_info.value).lower()
