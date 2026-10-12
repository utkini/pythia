import pytest
from sqlalchemy.engine import make_url

from pythia.database import async_database_url, create_engine


def test_supabase_postgres_url_is_adapted_for_asyncpg() -> None:
    result = async_database_url("postgresql://postgres:secret@example.supabase.co:5432/postgres?sslmode=require")
    assert result.startswith("postgresql+asyncpg://")
    assert "ssl=require" in result
    assert "sslmode" not in result
    assert make_url(result).password == "secret"


@pytest.mark.parametrize("scheme", ["postgres", "postgresql", "postgresql+asyncpg"])
@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("", {}),
        ("sslmode=require", {"ssl": "require"}),
        ("sslmode=verify-full", {"ssl": "verify-full"}),
        ("ssl=require", {"ssl": "require"}),
        ("ssl=require&sslmode=require", {"ssl": "require"}),
    ],
)
def test_postgres_url_normalization(scheme: str, query: str, expected: dict[str, str]) -> None:
    source = f"{scheme}://user:secret@localhost:5432/db"
    if query:
        source += f"?{query}"

    result = async_database_url(source)

    assert make_url(result).drivername == "postgresql+asyncpg"
    assert dict(make_url(result).query) == expected
    assert async_database_url(result) == result


def test_normalization_preserves_credentials_and_other_query_parameters() -> None:
    source = (
        "postgresql://postgres.project:p%40ss%3A%2F%25%23%3F@example.supabase.co:6543/postgres"
        "?sslmode=require&prepared_statement_cache_size=0&tag=one&tag=two"
    )

    result = make_url(async_database_url(source))
    original = make_url(source)

    assert result.username == original.username
    assert result.password == original.password == "p@ss:/%#?"
    assert result.host == original.host
    assert result.port == original.port
    assert result.database == original.database
    assert dict(result.query) == {
        "ssl": "require", "prepared_statement_cache_size": "0", "tag": ("one", "two"),
    }


@pytest.mark.parametrize("scheme", ["postgres", "postgresql", "postgresql+asyncpg"])
def test_conflicting_ssl_parameters_fail_without_exposing_credentials(scheme: str) -> None:
    source = f"{scheme}://private-user:private-password@private-host/db?ssl=require&sslmode=disable"

    with pytest.raises(ValueError, match="Conflicting ssl and sslmode") as error:
        async_database_url(source)

    for secret in (source, "private-user", "private-password", "private-host"):
        assert secret not in str(error.value)


@pytest.mark.parametrize("source", ["sqlite:///test.db", "postgresql+psycopg://user:secret@host/db"])
def test_other_dialects_are_unchanged(source: str) -> None:
    assert async_database_url(source) == source


@pytest.mark.parametrize("query", ["sslmode=require", ""])
async def test_engine_passes_normalized_connection_arguments_to_asyncpg(query: str) -> None:
    source = "postgresql://postgres:p%40ss%25@localhost:5432/postgres"
    if query:
        source += f"?{query}"
    engine = create_engine(source)
    try:
        _, arguments = engine.dialect.create_connect_args(engine.url)
        assert arguments["password"] == "p@ss%"
        assert arguments["user"] == "postgres"
        assert "sslmode" not in arguments
        if query:
            assert arguments["ssl"] == "require"
        else:
            assert "ssl" not in arguments
    finally:
        await engine.dispose()
