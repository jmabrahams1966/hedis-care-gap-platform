from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from .config import settings

# Encrypt the database connection in transit. Only applies to the real Postgres/
# Aurora driver — the SQLite dev/test URL takes no ssl arg. `require` encrypts
# without pinning the server cert; tighten to `verify-full` (with the RDS CA
# bundle shipped in the image) if a payer contract calls for it.
_connect_args: dict = {}
if settings.database_url.startswith("postgresql"):
    _connect_args["ssl"] = "require"

engine = create_async_engine(settings.database_url, echo=False, connect_args=_connect_args)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


class Base(DeclarativeBase):
    pass


async def get_db():
    async with SessionLocal() as session:
        yield session


async def init_db():
    """Dev convenience only — creates any missing tables against local SQLite on
    startup. Production schema changes go through Alembic (`backend/migrations/`),
    run explicitly as a deploy step, not on every app boot."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
