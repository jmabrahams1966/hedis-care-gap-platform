import os
import uuid

# Must happen before any `app.*` import — config/db module-level state reads
# these at import time.
_TEST_DB_PATH = f"./test_{uuid.uuid4().hex}.db"
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_TEST_DB_PATH}"
os.environ["DEV_MODE"] = "true"
os.environ["JWT_SECRET"] = "test-only-secret"

import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.db import SessionLocal, engine, init_db
from app.main import app
from app.seed import ensure_measure_catalog


@pytest_asyncio.fixture
async def client():
    """Only pulled in by tests that actually hit the API — pure unit tests
    (scoring, measures) don't depend on this and never touch the DB."""
    await init_db()
    async with SessionLocal() as db:
        await ensure_measure_catalog(db)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    await engine.dispose()
    if os.path.exists(_TEST_DB_PATH):
        os.remove(_TEST_DB_PATH)
