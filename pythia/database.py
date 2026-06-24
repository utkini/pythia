from collections.abc import AsyncIterator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine


def async_database_url(database_url: str) -> str:
    if database_url.startswith('postgresql+asyncpg://'):
        return database_url
    if database_url.startswith('postgresql://'):
        return database_url.replace('postgresql://', 'postgresql+asyncpg://', 1)
    if database_url.startswith('postgres://'):
        return database_url.replace('postgres://', 'postgresql+asyncpg://', 1)
    return database_url


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
