"""Fixtures for the database-backed tests.

Everything here is gated on TEST_DATABASE_URL. Unset it and this file adds
nothing: the pre-existing pure-function tests in test_quality_decision.py
still collect and run on a machine with no Postgres at all.

Getting a value for TEST_DATABASE_URL:
  * a local `postgres:16` (docker run, or a docker-compose service), or
  * a Neon branch (`neonctl branches create`) -- instant, isolated, disposable.

Never point it at DATABASE_URL. The fixture below refuses to run rather than
risk migrating over a real database.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import psycopg
import pytest
from psycopg.rows import dict_row

APP_DIR = Path(__file__).resolve().parent.parent
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))


def _test_url() -> str | None:
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        return None
    if url == os.environ.get("DATABASE_URL"):
        pytest.fail(
            "TEST_DATABASE_URL must not equal DATABASE_URL -- refusing to "
            "run destructive schema tests against what looks like the real "
            "database."
        )
    return url


@pytest.fixture(scope="session")
def db_url() -> str:
    url = _test_url()
    if url is None:
        pytest.skip("TEST_DATABASE_URL not set; database tests skipped")
    return url


@pytest.fixture(scope="session")
def migrated_db(db_url: str) -> str:
    """Drop, recreate, and provision the schema from migrations/ once per run.

    Applying the real migration files here means this fixture doubles as the
    migration test's provisioning step and as every other test's setup --
    there is exactly one path that creates the schema, and it is the one
    users run too.
    """
    with psycopg.connect(db_url, autocommit=True) as conn:
        conn.execute("DROP SCHEMA public CASCADE")
        conn.execute("CREATE SCHEMA public")

    # Import here, after sys.path is set up, and with DATABASE_URL pointed at
    # the test database for the duration of the call -- migrate.py reads it
    # from the environment.
    import migrate

    old_url = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = db_url
    try:
        exit_code = migrate.migrate()
    finally:
        if old_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = old_url

    assert exit_code == 0, "migrate.py failed against a fresh schema"
    return db_url


@pytest.fixture
def cur(migrated_db: str):
    """A cursor inside a transaction that is ALWAYS rolled back.

    This is what the "repositories never commit" rule buys: perfect
    isolation between tests with no truncation, no teardown SQL, and no
    ordering dependence between test functions.
    """
    with psycopg.connect(migrated_db, row_factory=dict_row) as conn:
        with conn.cursor() as cursor:
            try:
                yield cursor
            finally:
                conn.rollback()


@pytest.fixture
def user_id(cur) -> int:
    """A throwaway user row, for tests that need a valid FK target."""
    cur.execute(
        "INSERT INTO users (user_name, user_email, user_password_hash, timezone) "
        "VALUES ('Test User', 'test@example.com', 'x', 'America/Toronto') "
        "RETURNING user_id"
    )
    return cur.fetchone()["user_id"]


@pytest.fixture
def meal_id(cur, user_id: int) -> int:
    """A bare meal row with no images or analysis, for tests that need one."""
    cur.execute(
        "INSERT INTO meals (user_id, source) VALUES (%s, 'web_upload') "
        "RETURNING meal_id",
        (user_id,),
    )
    return cur.fetchone()["meal_id"]


@pytest.fixture
def app_db(migrated_db: str, monkeypatch):
    """Route repositories.base.tx() at the test database, one connection per call.

    db.py's connection pool is a process-wide lru_cache'd singleton keyed to
    whatever DATABASE_URL was set the first time it was touched -- exactly
    right for the running app, wrong for a test suite that must never let the
    real DATABASE_URL leak into a test transaction. Rather than fight the
    pool's caching, this bypasses it: it patches the one function
    repositories.base.tx() calls, so every repository call in the test -- and
    every orchestration function in meals.py that calls tx() -- lands on
    migrated_db without touching db.py or its pool at all.
    """
    import contextlib

    import repositories.base as repo_base

    @contextlib.contextmanager
    def _direct_connection():
        with psycopg.connect(migrated_db, row_factory=dict_row) as conn:
            yield conn

    monkeypatch.setattr(repo_base, "get_connection", _direct_connection)
    return migrated_db


@pytest.fixture
def committed_user_id(app_db: str):
    """A user that is REALLY committed, for tests that exercise app_db.

    The rollback-based `user_id` fixture creates its row inside a transaction
    on its own connection and never commits it -- invisible to any other
    connection, including the fresh ones `app_db` opens per call to mirror
    meals.py's real multi-transaction behaviour. A row an orchestration test
    needs as a foreign key has to actually be there, so this fixture commits
    for real and deletes (cascading through meals) for real at teardown.
    """
    with psycopg.connect(app_db, row_factory=dict_row) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "INSERT INTO users (user_name, user_email, user_password_hash, timezone) "
                "VALUES ('Flow Test', 'flow-test@example.com', 'x', 'America/Toronto') "
                "RETURNING user_id"
            )
            uid = cursor.fetchone()["user_id"]
        conn.commit()

    yield uid

    with psycopg.connect(app_db) as conn:
        conn.execute("DELETE FROM users WHERE user_id = %s", (uid,))
        conn.commit()
