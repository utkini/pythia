from collections.abc import AsyncIterator

from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine


def async_database_url(database_url: str) -> str:
    """Adapt PostgreSQL URLs and their SSL option for the asyncpg dialect."""
    if not database_url.startswith(("postgres://", "postgresql://", "postgresql+asyncpg://")):
        return database_url

    url = make_url(database_url).set(drivername="postgresql+asyncpg")
    query = dict(url.query)
    if "sslmode" in query:
        sslmode = query.pop("sslmode")
        if "ssl" in query and query["ssl"] != sslmode:
            raise ValueError("Conflicting ssl and sslmode database URL parameters.")
        query["ssl"] = sslmode
    return url.set(query=query).render_as_string(hide_password=False)


def create_engine(database_url: str) -> AsyncEngine:
    return create_async_engine(async_database_url(database_url), pool_pre_ping=True)


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


async def check_database(engine: AsyncEngine) -> None:
    async with engine.connect() as connection:
        await connection.execute(text("SELECT 1"))


async def session_scope(factory: async_sessionmaker[AsyncSession]) -> AsyncIterator[AsyncSession]:
    async with factory() as session:
        yield session
