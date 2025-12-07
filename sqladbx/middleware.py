from sqlalchemy.engine.url import URL
from sqlalchemy.ext.asyncio import AsyncEngine
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.types import ASGIApp

from .engine import create_engine
from .proxy import db


class SQLAlchemyMiddleware(BaseHTTPMiddleware):
    def __init__(
        self,
        app: ASGIApp,
        db_url: str | URL | None = None,
        custom_engine: AsyncEngine | None = None,
        engine_args: dict | None = None,
        session_args: dict | None = None,
        commit_on_exit: bool = False,
    ):
        super().__init__(app)
        self.commit_on_exit = commit_on_exit

        engine = create_engine(db_url, custom_engine, engine_args)
        db.initialize(engine, session_args)

    async def dispatch(self, request: Request, call_next):
        async with db(commit_on_exit=self.commit_on_exit):
            return await call_next(request)
