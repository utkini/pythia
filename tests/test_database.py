from sqlalchemy.engine import make_url

from pythia.database import async_database_url


def test_supabase_postgres_url_is_adapted_for_asyncpg() -> None:
    result = async_database_url("postgresql://postgres:secret@example.supabase.co:5432/postgres?sslmode=require")
    assert result.startswith("postgresql+asyncpg://")
    assert "ssl=require" in result
    assert "sslmode" not in result
    assert make_url(result).password == "secret"
