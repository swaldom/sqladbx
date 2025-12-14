# sqladbx 🚀

Modern async SQLAlchemy database context manager for **FastAPI**, **Litestar**, **Taskiq**, **Temporal**, and more.

[![PyPI version](https://badge.fury.io/py/sqladbx.svg)](https://badge.fury.io/py/sqladbx)
[![Python 3.13+](https://img.shields.io/badge/python-3.13+-ffdb66?style=flat&labelColor=255073)](https://www.python.org/)
[![Checked with mypy](https://www.mypy-lang.org/static/mypy_badge.svg)](https://mypy-lang.org/)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![pre-commit](https://img.shields.io/badge/pre--commit-1f2d23?logo=pre-commit&labelColor=grey)](https://github.com/pre-commit/pre-commit)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

> 💡 Inspired by [fastapi-async-sqlalchemy](https://github.com/h0rn3t/fastapi-async-sqlalchemy) - reimagined with modern async patterns, ContextVar-based session management, and extended framework support.

## ✨ Features

- 🎯 **Simple API** - Clean, intuitive interface for database operations
- ⚡ **Async-first** - Built for async/await with SQLAlchemy 2.0+
- 🔄 **Auto Context Management** - Automatic session lifecycle with middleware
- 🌐 **Framework Agnostic** - Use with web frameworks, CLI scripts, background tasks, or any async Python code
- 🎭 **Multi-Session Support** - Handle multiple concurrent sessions when needed
- 🔒 **Type Safe** - Full type hints and mypy support
- 🧪 **Well Tested** - Comprehensive test coverage

## 📦 Installation

```bash
pip install sqladbx
```

## 🚀 Quick Start

### FastAPI Example

```python
from fastapi import FastAPI
from sqlmodel import Field, SQLModel
from sqladbx import SQLAlchemyMiddleware, db

# Define your model
class User(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str
    email: str

# Create FastAPI app
app = FastAPI()

# Add SQLAlchemy middleware
app.add_middleware(
    SQLAlchemyMiddleware,
    db_url="postgresql+asyncpg://user:password@localhost/dbname"
)

# Use db.session in your endpoints - no context manager needed!
@app.post("/users")
async def create_user(name: str, email: str):
    user = User(name=name, email=email)
    db.session.add(user)
    await db.session.commit()
    await db.session.refresh(user)
    return user

@app.get("/users")
async def list_users():
    result = await db.session.scalars(select(User))
    return result.all()
```

## Without Middleware (Taskiq, Temporal, etc.)

```python
from sqladbx import db

# Initialize once at startup
db.initialize(db_url="postgresql+asyncpg://user:pass@localhost/dbname")

# Use in your code
async def process_data():
    async with db(commit_on_exit=True):
        result = await db.session.scalars(select(User))
        users = result.all()
        # Process users...

# Cleanup on shutdown (optional but recommended)
await db.dispose()
```

## Multi-Session Mode (Concurrent Queries)

```python
import asyncio
from sqladbx import db

async def query1():
    result = await db.session.execute(select(User))
    return result.scalars().all()

async def query2():
    result = await db.session.execute(select(Post))
    return result.scalars().all()

# Run queries concurrently
async with db(multi_sessions=True):
    users, posts = await asyncio.gather(query1(), query2())
```

## Multiple Databases

```python
from sqladbx import create_middleware_and_db

# Create db instances and middlewares
MainMiddleware, main_db = create_middleware_and_db()
ReplicaMiddleware, replica_db = create_middleware_and_db()

# Add to app
app.add_middleware(MainMiddleware, db_url="postgresql://main")
app.add_middleware(ReplicaMiddleware, db_url="postgresql://replica")

@app.get("/users")
async def list_users():
    # Use main_db for writes
    result = await main_db.session.scalars(select(User))
    return result.all()

@app.get("/stats")
async def get_stats():
    # Use replica_db for reads
    result = await replica_db.session.scalars(select(Stats))
    return result.all()
```

## More Examples

See the `examples/` directory for complete working examples:

- `examples/fastapi_basic.py`
- `examples/fastapi_multi_db.py`
- `examples/litestar_basic.py`
- `examples/litestar_multi_db.py`
- `examples/taskiq_basic.py`
- `examples/taskiq_multi_sessions.py`

## 🎓 Best Practices

### ✅ DO

- Use middleware for web applications (automatic session management)
- Use manual context (`async with db()`) for CLI/background tasks
- Enable `commit_on_exit=True` for simple CRUD operations
- Use separate db proxies for master/replica setups
- Implement proper error handling with try/except

### ❌ DON'T

- Don't mix middleware and manual initialization
- Don't create sessions manually - use `db.session`
- Don't use blocking I/O inside database contexts
- Don't share sessions between requests

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🔗 Links

- **PyPI**: <https://pypi.org/project/sqladbx/>
- **GitHub**: <https://github.com/swaldom/sqladbx>
- **Documentation**: <https://github.com/swaldom/sqladbx#readme>
- **Issues**: <https://github.com/swaldom/sqladbx/issues>

## 💬 Support

If you have any questions or need help, please:

- Open an issue on GitHub
- Check existing issues and discussions
- Read the documentation carefully

---

Made with ❤️ by [Oleksii Svichkar](https://github.com/swaldom)
