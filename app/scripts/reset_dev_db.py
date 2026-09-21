"""DESTRUCTIVE. DEV ONLY. Drops and recreates the public schema.

The psql-free equivalent of scripts/reset_dev_db.sql, for machines without a
Postgres client installed.

    python scripts/reset_dev_db.py            # dry run: prints the target
    python scripts/reset_dev_db.py --yes      # actually does it

Deliberately not a flag on migrate.py. Keeping the migration runner incapable
of destroying anything is worth more than saving a command: a mis-set
DATABASE_URL should be an error, not a lost database.

Dropping the schema also drops schema_migrations, so `python migrate.py`
afterwards re-applies from 0001 with no orphan version rows.

This does NOT touch R2. Purge the `users/` prefix separately -- meal_id
restarts at 1 and object keys embed it, so a new meal 1 would collide with the
old meal 1's object and serve a stale image.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

load_dotenv(BASE_DIR / ".env")

from db import get_database_url  # noqa: E402  (needs .env loaded first)


def _target(url: str) -> str:
    """Host and database name only -- never the credentials."""
    parts = urlsplit(url)
    host = parts.hostname or "?"
    database = (parts.path or "/?").lstrip("/") or "?"
    return f"{database} @ {host}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--yes",
        action="store_true",
        help="required to actually drop anything; without it this only reports",
    )
    args = parser.parse_args()

    try:
        url = get_database_url()
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(f"target: {_target(url)}")

    if not args.yes:
        print("\nDry run. This WOULD drop every table, view and function in")
        print("the public schema, including schema_migrations.")
        print("Re-run with --yes to proceed.")
        return 0

    import psycopg

    print("\ndropping public schema ... ", end="", flush=True)
    with psycopg.connect(url, autocommit=True) as conn:
        conn.execute("DROP SCHEMA public CASCADE")
        conn.execute("CREATE SCHEMA public")
    print("ok")
    print("\nNow run:  python migrate.py")
    print("And purge the R2 `users/` prefix if this database had uploads.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
