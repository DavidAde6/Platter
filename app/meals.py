from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from psycopg.types.json import Jsonb
from pydantic import BaseModel

from db import get_connection
from graph import run_image_quality_graph
from image_quality import analyze_image_quality
from quality_decision import evaluate_quality
from storage import is_r2_configured, resolve_meal_urls, upload_meal_images


class MealPublic(BaseModel):
    meal_id: int
    image_url: str | None
    thumbnail_url: str | None
    source: str
    status: str
    created_at: datetime
    processed_at: datetime | None
    rejection_reason: str | None
    image_format: str | None = None
    image_type: str | None = None


class MealUploadResponse(BaseModel):
    meal_id: int
    status: str
    image_url: str | None = None
    thumbnail_url: str | None = None
    metadata: dict[str, Any]
    # User-facing reason when the photo is rejected (status == "rejected").
    message: str | None = None


def _parse_exif_datetime(value: Any) -> datetime | None:
    if not value or not isinstance(value, str):
        return None
    for fmt in ("%Y:%m:%d %H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(value, fmt).replace(tzinfo=UTC)
        except ValueError:
            continue
    return None


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _infer_likely_meal_type(captured_at: datetime | None) -> str:
    """Infer the meal type from the photo's local capture hour.

    EXIF DateTimeOriginal has no timezone, so its wall-clock hour already
    reflects local time where the photo was taken -- ideal for this. Without a
    capture time there's nothing to infer from, so we fall back to 'unknown'.
    """
    if captured_at is None:
        return "unknown"

    hour = captured_at.hour
    if 5 <= hour < 11:
        return "breakfast"
    if 11 <= hour < 16:
        return "lunch"
    if 16 <= hour < 22:
        return "dinner"
    return "unknown"


def _context_row_values(meal_id: int, metadata: dict[str, Any]) -> tuple[Any, ...]:
    captured_at = _parse_exif_datetime(
        metadata.get("datetime_original") or metadata.get("datetime")
    )
    likely_meal_type = _infer_likely_meal_type(captured_at)
    # city/country require reverse-geocoding the EXIF GPS coordinates; left
    # NULL for now until a geocoding source is wired in.
    return (meal_id, likely_meal_type, None, None)


def _metadata_row_values(meal_id: int, metadata: dict[str, Any]) -> tuple[Any, ...]:
    dpi = metadata.get("dpi") or {}
    captured_at = _parse_exif_datetime(
        metadata.get("datetime_original") or metadata.get("datetime")
    )
    flash = metadata.get("flash")
    return (
        meal_id,
        metadata.get("image_format"),
        metadata.get("image_type"),
        metadata.get("is_animated"),
        metadata.get("n_frames"),
        _as_float(dpi.get("x")),
        _as_float(dpi.get("y")),
        _as_int(metadata.get("orientation")),
        metadata.get("make"),
        metadata.get("model"),
        _as_float(metadata.get("focal_length")),
        _as_int(metadata.get("iso")),
        str(flash) if flash is not None else None,
        metadata.get("lens_model"),
        captured_at,
    )


def create_meal_with_metadata(
    user_id: int,
    source: str,
    metadata: dict[str, Any],
    content: bytes,
    content_type: str,
    filename: str | None,
) -> MealUploadResponse:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO meal_uploads (user_id, source, status, processed_at)
                VALUES (%s, %s, 'processing', NULL)
                RETURNING meal_id, status
                """,
                (user_id, source),
            )
            row = cur.fetchone()
            meal_id = row["meal_id"]

            if not is_r2_configured():
                raise RuntimeError(
                    "Cloudflare R2 is not configured. Set R2_ACCOUNT_ID, "
                    "R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, and R2_BUCKET_NAME."
                )

            image_key, thumbnail_key = upload_meal_images(
                user_id,
                meal_id,
                content,
                content_type,
                filename,
            )
            # detected_issues combines the deterministic OpenCV checks
            # (`technical`) with the LangGraph vision node's analysis (`vision`).
            detected_issues = {
                "technical": analyze_image_quality(content),
                "vision": run_image_quality_graph(content),
            }
            # Gate the meal on is_food_image, the vision recommended_action, and
            # the technical checks. The image is stored either way (per spec);
            # rejected meals carry a user-facing rejection_reason.
            decision = evaluate_quality(detected_issues)
            status = "completed" if decision.accepted else "rejected"

            cur.execute(
                """
                UPDATE meal_uploads
                SET image_url = %s,
                    thumbnail_url = %s,
                    status = %s,
                    rejection_reason = %s,
                    processed_at = NOW()
                WHERE meal_id = %s
                RETURNING status
                """,
                (image_key, thumbnail_key, status, decision.message, meal_id),
            )
            row = cur.fetchone()

            cur.execute(
                """
                INSERT INTO image_metadata (
                    meal_id, image_format, image_type, is_animated, n_frames,
                    dpi_x, dpi_y, orientation, make, model, focal_length,
                    iso, flash, lens_model, captured_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                _metadata_row_values(meal_id, metadata),
            )

            cur.execute(
                """
                INSERT INTO meal_contexts (
                    meal_id, likely_meal_type, city, country
                ) VALUES (%s, %s, %s, %s)
                """,
                _context_row_values(meal_id, metadata),
            )

            cur.execute(
                """
                INSERT INTO image_qualities (
                    meal_id, is_food_image, food_confidence,
                    detected_issues, recommended_action, usability_status
                ) VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    meal_id,
                    decision.is_food_image,
                    decision.food_confidence,
                    Jsonb(detected_issues),
                    decision.recommended_action,
                    decision.usability_status,
                ),
            )
            conn.commit()

    resolved = resolve_meal_urls(
        {
            "meal_id": meal_id,
            "image_url": image_key,
            "thumbnail_url": thumbnail_key,
        }
    )

    return MealUploadResponse(
        meal_id=meal_id,
        status=row["status"],
        image_url=resolved["image_url"],
        thumbnail_url=resolved["thumbnail_url"],
        metadata=metadata,
        message=decision.message,
    )


def list_meals_for_user(user_id: int) -> list[MealPublic]:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    m.meal_id,
                    m.image_url,
                    m.thumbnail_url,
                    m.source,
                    m.status,
                    m.created_at,
                    m.processed_at,
                    m.rejection_reason,
                    im.image_format,
                    im.image_type
                FROM meal_uploads m
                LEFT JOIN image_metadata im ON im.meal_id = m.meal_id
                WHERE m.user_id = %s
                ORDER BY m.created_at DESC
                """,
                (user_id,),
            )
            rows = cur.fetchall()

    return [MealPublic(**resolve_meal_urls(row)) for row in rows]


# Maps the public ?variant= query param to its stored object-key column.
_VARIANT_COLUMNS = {
    "original": "image_url",
    "thumbnail": "thumbnail_url",
}


def get_meal_image_key(user_id: int, meal_id: int, variant: str) -> str | None:
    """Return the R2 object key for a meal image, but only if the meal
    belongs to this user. Returns None when the meal does not exist, is not
    owned by the user, or has no image for the requested variant.

    This ownership check is the safety win a presigned/public URL can't give:
    access is gated on the authenticated caller actually owning the meal.
    """
    column = _VARIANT_COLUMNS.get(variant)
    if column is None:
        return None

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                # `column` is selected from a fixed whitelist above, never user input.
                f"""
                SELECT {column} AS object_key
                FROM meal_uploads
                WHERE meal_id = %s AND user_id = %s
                """,
                (meal_id, user_id),
            )
            row = cur.fetchone()

    if row is None:
        return None
    return row["object_key"]
