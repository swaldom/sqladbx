"""Custom exceptions for SQLAlchemy session management."""


class MissingSessionError(Exception):
    """Exception raised for when the user tries to access a database session before it is created."""

    def __init__(self) -> None:
        """Initialize MissingSessionError."""
        msg = """
        No session found! Either you are not currently in a request context,
        or you need to manually create a session context by using a `db` instance as
        a context manager e.g.:

        async with db():
            await db.session.execute(foo.select()).fetchall()
        """
        super().__init__(msg)


class SessionNotInitializedError(Exception):
    """Exception raised when the user creates a new DB session without first initializing it."""

    def __init__(self) -> None:
        """Initialize SessionNotInitializedError."""
        msg = """
        Session not initialized! Ensure that SQLAlchemyMiddleware has been initialized before
        attempting database access.
        """
        super().__init__(msg)
