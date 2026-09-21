import os
from contextlib import contextmanager
from functools import lru_cache

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

# Upper bound on pooled connections. One upload now runs three short
# transactions instead of one long one, so the pool is what keeps that from
# multiplying into Neon's connection ceiling. Override per environment.
DEFAULT_POOL_MAX_SIZE = 5

# Hold nothing open when idle. Neon scales compute to zero, and a connection
# parked in the pool defeats that -- it keeps the endpoint awake and billing
# for a dev database nobody is using. The cost is a cold start on the first
# request after an idle period. Raise to 1 once there is steady traffic.
DEFAULT_POOL_MIN_SIZE = 0


def get_database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL is not set")
    return url


@lru_cache(maxsize=1)
def _pool() -> ConnectionPool:
    """One pool per process, built on first use.

    Lazy on purpose. ``migrate.py`` imports this module before it calls
    ``load_dotenv()``, so reading DATABASE_URL at import time would raise on
    every invocation outside an already-exported shell. Same lazy-singleton
    pattern as ``storage._get_client()`` and ``graph.nodes._client()``.

    ``check`` matters specifically for Neon: it autosuspends idle compute and
    drops the TCP connections with it, so a pooled connection can be dead by
    the time it is handed out. The check reconnects instead of surfacing that
    as a query error.
    """
    max_size = int(os.environ.get("DB_POOL_MAX_SIZE", DEFAULT_POOL_MAX_SIZE))
    min_size = int(os.environ.get("DB_POOL_MIN_SIZE", DEFAULT_POOL_MIN_SIZE))
    return ConnectionPool(
        get_database_url(),
        min_size=min_size,
        max_size=max_size,
        # Recycle rather than hold forever: Neon's pooler and its autosuspend
        # both retire connections on their own schedule.
        max_idle=60,
        max_lifetime=1800,
        timeout=10.0,
        kwargs={
            "row_factory": dict_row,
            # MANDATORY against Neon's -pooler endpoint, which is PgBouncer in
            # transaction mode. psycopg3 silently starts server-side preparing
            # a statement after its 5th execution, and a prepared statement
            # does not survive being handed a different backend -- so this
            # surfaces as intermittent "prepared statement does not exist"
            # errors only once a query gets warm. Harmless on a direct
            # connection, so it is set unconditionally rather than sniffed
            # from the hostname.
            "prepare_threshold": None,
        },
        check=ConnectionPool.check_connection,
        open=True,
    )


@contextmanager
def get_connection():
    """Borrow a pooled connection for the duration of the block.

    Unchanged contract: commits on clean exit, rolls back on exception, and
    yields a connection whose cursors return dicts. Callers that need several
    independent transactions should use several ``with`` blocks rather than
    one long one -- that is the whole point of the split in meals.py.
    """
    with _pool().connection() as conn:
        yield conn


@contextmanager
def connect_direct():
    """A single unpooled connection, for short-lived scripts.

    Pooling a process that runs one batch of statements and exits buys
    nothing and costs a background maintenance thread that has to be shut
    down cleanly. Migrations and the dev-reset script use this; the API uses
    the pool.
    """
    with psycopg.connect(get_database_url(), row_factory=dict_row) as conn:
        yield conn


def close_pool() -> None:
    """Shut the pool down. For a FastAPI lifespan handler or a test teardown."""
    if _pool.cache_info().currsize:
        _pool().close()
        _pool.cache_clear()


def check_connection() -> bool:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 AS ok")
            row = cur.fetchone()
            return row is not None and row["ok"] == 1
