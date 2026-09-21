"""Minimal forward-only migration runner.

Applies the numbered .sql files in ``migrations/`` in filename order, tracking
what has run in a ``schema_migrations`` table. Alembic is deliberately not used
here: the app talks to Postgres through raw psycopg with hand-written SQL, so
there is no model metadata for Alembic to autogenerate from, and its migration
environment would be pure overhead.

Usage (from ``app/``, with DATABASE_URL set):

    python migrate.py            # apply everything pending
    python migrate.py --status   # show applied / pending, change nothing
    python migrate.py --dry-run  # print what would run, change nothing

Migrations are forward-only; there are no down-scripts. To undo something,
write a new migration. Each file applies inside its own transaction, so a
failure leaves that migration fully rolled back and later ones untouched.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from dotenv import load_dotenv

from db import connect_direct

BASE_DIR = Path(__file__).parent
MIGRATIONS_DIR = BASE_DIR / "migrations"

# db.py reads DATABASE_URL straight from the environment; main.py is what
# normally loads .env into it. This is a separate entry point, so it has to do
# the same or every invocation outside an active shell export fails.
load_dotenv(BASE_DIR / ".env")

_CREATE_TRACKING_TABLE = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version     TEXT PRIMARY KEY,
    applied_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
)
"""


def discover_migrations() -> list[Path]:
    """Every .sql file in migrations/, ordered by filename.

    The numeric prefix is what orders them, so zero-pad new files to keep
    string sort and numeric order in agreement (0010 sorts after 0009).
    """
    if not MIGRATIONS_DIR.is_dir():
        return []
    return sorted(MIGRATIONS_DIR.glob("*.sql"))


def _applied_versions(cur) -> set[str]:
    cur.execute("SELECT version FROM schema_migrations")
    return {row["version"] for row in cur.fetchall()}


def _pending(cur) -> list[Path]:
    applied = _applied_versions(cur)
    return [p for p in discover_migrations() if p.stem not in applied]


def status() -> int:
    with connect_direct() as conn:
        with conn.cursor() as cur:
            cur.execute(_CREATE_TRACKING_TABLE)
            conn.commit()
            applied = _applied_versions(cur)

    migrations = discover_migrations()
    if not migrations:
        print(f"No migrations found in {MIGRATIONS_DIR}")
        return 0

    for path in migrations:
        mark = "applied" if path.stem in applied else "PENDING"
        print(f"  [{mark:>7}]  {path.name}")

    # Versions recorded in the DB with no matching file — usually a migration
    # deleted after being applied, or a checkout that predates it.
    orphans = applied - {p.stem for p in migrations}
    for version in sorted(orphans):
        print(f"  [ orphan]  {version}  (recorded in DB, no file on disk)")

    pending_count = sum(1 for p in migrations if p.stem not in applied)
    print(f"\n{pending_count} pending, {len(applied)} applied.")
    return 0


def migrate(dry_run: bool = False) -> int:
    with connect_direct() as conn:
        with conn.cursor() as cur:
            cur.execute(_CREATE_TRACKING_TABLE)
            conn.commit()
            pending = _pending(cur)

            if not pending:
                print("Nothing to apply — schema is up to date.")
                return 0

            if dry_run:
                print(f"Would apply {len(pending)} migration(s):")
                for path in pending:
                    print(f"  {path.name}")
                return 0

            for path in pending:
                sql = path.read_text(encoding="utf-8")
                print(f"Applying {path.name} ... ", end="", flush=True)
                try:
                    cur.execute(sql)
                    cur.execute(
                        "INSERT INTO schema_migrations (version) VALUES (%s)",
                        (path.stem,),
                    )
                    conn.commit()
                except Exception as exc:
                    conn.rollback()
                    print("FAILED")
                    print(f"\n{path.name} rolled back. Nothing after it ran.\n{exc}")
                    return 1
                print("ok")

    print(f"\nApplied {len(pending)} migration(s).")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--status",
        action="store_true",
        help="show applied and pending migrations, change nothing",
    )
    group.add_argument(
        "--dry-run",
        action="store_true",
        help="list migrations that would be applied, change nothing",
    )
    args = parser.parse_args()

    try:
        if args.status:
            return status()
        return migrate(dry_run=args.dry_run)
    except RuntimeError as exc:
        # get_database_url() raises this when DATABASE_URL is unset.
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
