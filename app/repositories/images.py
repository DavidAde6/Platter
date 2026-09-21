"""Stored image variants and their EXIF."""

from __future__ import annotations

from typing import Any

from psycopg import Cursor
from psycopg.types.json import Jsonb

from repositories.read_models import ImageRef


def insert_image(
    cur: Cursor,
    *,
    meal_id: int,
    role: str,
    object_key: str,
    content_type: str,
    byte_size: int,
    sha256: str,
    image_format: str | None = None,
    width: int | None = None,
    height: int | None = None,
) -> int:
    """Record a variant that is already in R2.

    ON CONFLICT so a retry -- a re-upload, or a thumbnail that succeeds on a
    second attempt -- is idempotent rather than a unique violation.

    Call this only AFTER the object exists. The row asserts that the bytes are
    addressable, and object_key is NOT NULL precisely so that assertion cannot
    be made falsely.
    """
    cur.execute(
        """
        INSERT INTO meal_images (
            meal_id, role, object_key, content_type, image_format,
            byte_size, width, height, sha256
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (meal_id, role) DO UPDATE SET
            object_key   = EXCLUDED.object_key,
            content_type = EXCLUDED.content_type,
            image_format = EXCLUDED.image_format,
            byte_size    = EXCLUDED.byte_size,
            width        = EXCLUDED.width,
            height       = EXCLUDED.height,
            sha256       = EXCLUDED.sha256
        RETURNING image_id
        """,
        (
            meal_id,
            role,
            object_key,
            content_type,
            image_format,
            byte_size,
            width,
            height,
            sha256,
        ),
    )
    return cur.fetchone()["image_id"]


def insert_exif(
    cur: Cursor,
    *,
    meal_id: int,
    has_exif: bool,
    exif: dict[str, Any],
) -> None:
    """Store the metadata dict whole.

    Deliberately not a column list. The extractor produces roughly twice as
    many fields as the old table kept, and the dropped ones were unrecoverable.
    """
    cur.execute(
        """
        INSERT INTO meal_image_exif (meal_id, has_exif, exif)
        VALUES (%s, %s, %s)
        ON CONFLICT (meal_id) DO UPDATE SET
            has_exif = EXCLUDED.has_exif,
            exif     = EXCLUDED.exif
        """,
        (meal_id, has_exif, Jsonb(exif)),
    )


def get_object_ref(
    cur: Cursor, *, user_id: int, meal_id: int, role: str
) -> ImageRef | None:
    """The R2 key for one variant, but only if this user owns the meal.

    ``role`` is a bound parameter, which is what retires the old
    ``_VARIANT_COLUMNS`` map and its column name interpolated into an f-string.

    The user_id predicate is the access control the image proxy depends on --
    the reason the app serves bytes itself instead of handing out presigned
    URLs. Returns None for a missing meal, a meal owned by someone else, and a
    variant that was never stored, because a caller should not be able to tell
    those apart.
    """
    cur.execute(
        """
        SELECT i.object_key, i.content_type
        FROM meal_images i
        JOIN meals m ON m.meal_id = i.meal_id
        WHERE i.meal_id = %s AND m.user_id = %s AND i.role = %s
        """,
        (meal_id, user_id, role),
    )
    row = cur.fetchone()
    return ImageRef(**row) if row else None
