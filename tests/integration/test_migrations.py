"""Run only when PYTHIA_TEST_DATABASE_URL points at an isolated PostgreSQL database."""

import os

import pytest
from alembic import command
from alembic.config import Config


@pytest.mark.skipif(not os.getenv("PYTHIA_TEST_DATABASE_URL"), reason="requires isolated PostgreSQL")
def test_migrations_apply(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", os.environ["PYTHIA_TEST_DATABASE_URL"])
    config = Config("alembic.ini")
    command.upgrade(config, "head")
    command.downgrade(config, "20260623_0001")
    command.upgrade(config, "head")
