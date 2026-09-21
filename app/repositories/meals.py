"""Meal rows, and the two read views built over them.

All reads go through v_meal_list / v_meal_detail. No caller of this module
sees a JSONB path, a join, or the derived-status CASE.
"""

from __future__ import annotations

from datetime import datetime

from psycopg import Cursor

from repositories.read_models import MealDetailRow, MealListRow

# Columns of v_meal_list, in one place. The view is the contract; this list is
# how we notice when it changes.
_LIST_COLUMNS = """
    meal_id, user_id, source, created_at, lifecycle, status,
    nutrition_ready, nutrition_blocked_reason, rejection_reason,
    image_format, width, height, has_original, has_thumbnail,
    likely_meal_type, meal_time_source, processed_at
"""


def insert_meal(
    cur: Cursor,
    *,
    user_id: int,
    source: str,
    captured_at_local: datetime | None = None,
    captured_at_offset_minutes: int | None = None,
) -> int:
    """Create the meal row. Lifecycle starts at 'pending' by default.

    This is transaction one of the upload: it exists before the bytes do,
    because the R2 object key embeds meal_id.
    """
    cur.execute(
        """
        INSERT INTO meals (user_id, source, captured_at_local, captured_at_offset_minutes)
        VALUES (%s, %s, %s, %s)
        RETURNING meal_id
        """,
        (user_id, source, captured_at_local, captured_at_offset_minutes),
    )
    return cur.fetchone()["meal_id"]


def mark_stored(cur: Cursor, meal_id: int) -> None:
    """The bytes are in R2 and the image rows are written."""
    cur.execute(
        "UPDATE meals SET lifecycle = 'stored', stored_at = NOW() WHERE meal_id = %s",
        (meal_id,),
    )


def mark_failed(cur: Cursor, meal_id: int, reason: str) -> None:
    """Storage failed. ``reason`` is operator-facing and never shown to a user.

    Without this the meal would sit at 'pending' forever, indistinguishable
    from an analysis still running.
    """
    cur.execute(
        "UPDATE meals SET lifecycle = 'failed', failure_reason = %s WHERE meal_id = %s",
        (reason[:500], meal_id),
    )


def list_for_user(
    cur: Cursor,
    user_id: int,
    *,
    limit: int = 100,
    before: datetime | None = None,
) -> list[MealListRow]:
    """The Log query. Bounded, unlike the one it replaces."""
    if before is None:
        cur.execute(
            f"""
            SELECT {_LIST_COLUMNS}
            FROM v_meal_list
            WHERE user_id = %s
            ORDER BY created_at DESC
            LIMIT %s
            """,
            (user_id, limit),
        )
    else:
        cur.execute(
            f"""
            SELECT {_LIST_COLUMNS}
            FROM v_meal_list
            WHERE user_id = %s AND created_at < %s
            ORDER BY created_at DESC
            LIMIT %s
            """,
            (user_id, before, limit),
        )
    return [MealListRow(**row) for row in cur.fetchall()]


def get_detail(cur: Cursor, *, user_id: int, meal_id: int) -> MealDetailRow | None:
    """One meal with its verdict and foods, or None.

    The user_id predicate is the ownership check: another user's meal_id is
    indistinguishable from one that does not exist.
    """
    cur.execute(
        f"""
        SELECT {_LIST_COLUMNS},
               run_id, pipeline_version, run_status, usability_status,
               recommended_action, is_food_image, food_confidence,
               analysis_complete, rules_version, foods
        FROM v_meal_detail
        WHERE meal_id = %s AND user_id = %s
        """,
        (meal_id, user_id),
    )
    row = cur.fetchone()
    return MealDetailRow(**row) if row else None


def find_recent_by_hash(cur: Cursor, *, user_id: int, sha256: str) -> int | None:
    """The most recent meal of this user whose original has these exact bytes.

    Nothing calls this yet. Whether a re-upload of identical bytes should be
    the same meal is a product question, not a schema one -- this is the
    query that will answer it when the question is asked.
    """
    cur.execute(
        """
        SELECT i.meal_id
        FROM meal_images i
        JOIN meals m ON m.meal_id = i.meal_id
        WHERE m.user_id = %s AND i.role = 'original' AND i.sha256 = %s
        ORDER BY i.created_at DESC
        LIMIT 1
        """,
        (user_id, sha256),
    )
    row = cur.fetchone()
    return row["meal_id"] if row else None
