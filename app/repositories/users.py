"""User rows.

The service layer keeps the Pydantic request/response models and the password
hashing; this module owns the SQL and, with it, the translation of Postgres
error codes into domain errors. A service should not have to know what
sqlstate 23505 is.
"""

from __future__ import annotations

from typing import Any

import psycopg
from psycopg import Cursor

# The public projection. Excludes user_password_hash: a caller that wants the
# hash has to ask for it explicitly via get_by_email_with_hash().
_PUBLIC_COLUMNS = """
    user_id, user_name, user_email, daily_caloric_target,
    timezone, created_at, updated_at
"""


class EmailAlreadyExists(ValueError):
    """Raised instead of leaking a psycopg IntegrityError upward.

    Subclasses ValueError so the existing handler in main.py, which maps
    ValueError to a 409, keeps working unchanged.
    """

    def __init__(self) -> None:
        super().__init__("An account with this email already exists")


def get_by_id(cur: Cursor, user_id: int) -> dict[str, Any] | None:
    cur.execute(
        f"SELECT {_PUBLIC_COLUMNS} FROM users WHERE user_id = %s",
        (user_id,),
    )
    return cur.fetchone()


def get_by_email_with_hash(cur: Cursor, user_email: str) -> dict[str, Any] | None:
    """Public columns plus the password hash, for authentication only."""
    cur.execute(
        f"SELECT {_PUBLIC_COLUMNS}, user_password_hash FROM users WHERE user_email = %s",
        (user_email.lower(),),
    )
    return cur.fetchone()


def insert_user(
    cur: Cursor,
    *,
    user_name: str,
    user_email: str,
    password_hash: str,
    daily_caloric_target: int | None = None,
    timezone: str | None = None,
) -> dict[str, Any]:
    """Create a user. Email is lowercased to satisfy the table's CHECK."""
    try:
        cur.execute(
            f"""
            INSERT INTO users (
                user_name, user_email, user_password_hash,
                daily_caloric_target, timezone
            )
            VALUES (%s, %s, %s, %s, %s)
            RETURNING {_PUBLIC_COLUMNS}
            """,
            (
                user_name.strip(),
                user_email.lower(),
                password_hash,
                daily_caloric_target,
                timezone,
            ),
        )
    except psycopg.errors.UniqueViolation as exc:
        raise EmailAlreadyExists() from exc
    return cur.fetchone()


# Whitelist of updatable columns. The UPDATE below builds its SET clause
# dynamically, so the column names must come from here and never from a
# request body.
_UPDATABLE = {
    "user_name",
    "daily_caloric_target",
    "user_password_hash",
    "timezone",
}


def update_user(
    cur: Cursor, user_id: int, changes: dict[str, Any]
) -> dict[str, Any] | None:
    """Apply a partial update. Returns the updated row, or None if no such user.

    ``changes`` keys must be in _UPDATABLE; anything else is a programming
    error and raises rather than being silently dropped.
    """
    unknown = set(changes) - _UPDATABLE
    if unknown:
        raise ValueError(f"not updatable: {sorted(unknown)}")

    if not changes:
        return get_by_id(cur, user_id)

    assignments = ", ".join(f"{column} = %s" for column in changes)
    values = [*changes.values(), user_id]

    cur.execute(
        f"""
        UPDATE users
        SET {assignments}
        WHERE user_id = %s
        RETURNING {_PUBLIC_COLUMNS}
        """,
        values,
    )
    return cur.fetchone()
