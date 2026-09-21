"""Upload orchestration.

No SQL lives here any more -- that is repositories/. This module's job is to
sequence the work and, above all, to decide where transactions start and stop.

THE TRANSACTION SHAPE IS THE POINT OF THIS MODULE.

    T1  INSERT meals                              commit    (milliseconds)
        R2 upload                                           no DB connection held
    T2  INSERT meal_images, meal_image_exif        commit    (milliseconds)
        OpenCV + Claude                                     no DB connection held
    T3  INSERT run, artifacts, verdict             commit    (milliseconds)

The previous version held one connection and one open transaction across two
R2 round-trips and a vision model call -- 15 to 30 seconds of a pooled Neon
connection pinned on external I/O, with every row invisible until the very
end. Adding a second model call for M1 would have made it worse.

The request is still SYNCHRONOUS: the client gets its verdict in the response.
What changed is that nothing slow happens inside a transaction.

The visible consequence is that failure is now partial and recorded rather
than all-or-nothing and silent:

  * R2 fails            -> the meal exists, lifecycle 'failed', reason stored.
  * the model call dies -> the meal and its image exist and are 'stored'; no
                           run row, so the meal reads as 'processing'. The
                           photo is not lost, and a re-run is just a new run.

Previously either of those rolled the whole upload back and discarded the
user's photo along with any record that it happened.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable

from pydantic import BaseModel

from graph import run_image_quality_graph
from graph.builder import PIPELINE_VERSION
from graph.nodes import MODEL, PROMPT_VERSION
from image_quality import analyze_image_quality, analyzer_config_hash
from quality_decision import DECISION_RULES_VERSION, QualityDecision, evaluate_quality
from repositories import analysis as analysis_repo
from repositories import images as images_repo
from repositories import meals as meals_repo
from repositories.base import tx
from repositories.read_models import MealDetailRow, MealListRow
from storage import (
    ImageAsset,
    is_r2_configured,
    meal_image_paths,
    upload_meal_images,
)


class MealFood(BaseModel):
    """One identified food. Empty until the M1 visible_foods stage ships."""

    label: str
    possible_types: list[str] = []
    possible_preparations: list[str] = []
    confidence: float | None = None


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
    # Anything that renders a calorie or macro number must branch on this and
    # never on `status`: a photo can be stored and accepted while still being
    # ineligible for a nutrition estimate.
    nutrition_ready: bool = False
    likely_meal_type: str | None = None


class MealDetail(MealPublic):
    """GET /api/meals/{meal_id}: the list row plus verdict and foods."""

    width: int | None = None
    height: int | None = None
    nutrition_blocked_reason: str | None = None
    usability_status: str | None = None
    recommended_action: str | None = None
    is_food_image: bool | None = None
    food_confidence: float | None = None
    analysis_complete: bool | None = None
    meal_time_source: str | None = None
    foods: list[MealFood] = []


class MealUploadResponse(BaseModel):
    meal_id: int
    status: str
    image_url: str | None = None
    thumbnail_url: str | None = None
    metadata: dict[str, Any]
    # User-facing reason when the photo is rejected (status == "rejected").
    message: str | None = None
    nutrition_ready: bool = False


# ---------------------------------------------------------------------------
# EXIF handling
# ---------------------------------------------------------------------------

# Dropped before the metadata dict is stored. These are binary blobs that
# _serialize_exif_value() turns into long hex or replacement-char strings; kept
# verbatim they would push almost every exif row out of line into TOAST
# storage for data nothing reads.
_EXIF_PRUNE = frozenset(
    {"MakerNote", "UserComment", "PrintImageMatching", "ThumbnailData"}
)

# Any single serialized value longer than this is dropped too, as a backstop
# for whatever unusual tag a camera vendor invents next.
_MAX_EXIF_VALUE_CHARS = 4096


def _parse_exif_datetime(value: Any) -> datetime | None:
    """Parse EXIF DateTimeOriginal as a NAIVE local timestamp.

    Deliberately does not attach a timezone. The string is a wall-clock
    reading local to wherever the photo was taken, and EXIF carries no offset
    for it. The previous version stamped it as UTC, which produced a value
    that was correct as an hour and wrong as an instant -- fine for meal-type
    inference, silently wrong for ordering or arithmetic.
    """
    if not value or not isinstance(value, str):
        return None
    for fmt in ("%Y:%m:%d %H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None


def _exif_for_storage(metadata: dict[str, Any]) -> dict[str, Any]:
    """The metadata dict, minus the blobs, ready to store whole.

    Storing it whole is the point: the extractor produces roughly twice as
    many fields as the old column list kept -- including GPS, which was
    computed and then thrown away on every upload.
    """
    stored = dict(metadata)
    exif = stored.get("exif")
    if not isinstance(exif, dict):
        return stored

    kept: dict[str, Any] = {}
    pruned: list[str] = []
    for key, value in exif.items():
        too_long = isinstance(value, str) and len(value) > _MAX_EXIF_VALUE_CHARS
        if key in _EXIF_PRUNE or too_long:
            pruned.append(key)
            continue
        kept[key] = value

    stored["exif"] = kept
    if pruned:
        # Recorded so a missing tag reads as "we dropped this" rather than
        # "the camera did not write it".
        stored["exif_pruned"] = sorted(pruned)
    return stored


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------


@dataclass
class _StageResult:
    """One stage's output, ready to become an analysis_artifacts row."""

    stage: str
    payload: dict[str, Any]
    latency_ms: int
    model_id: str | None = None
    prompt_version: str | None = None
    config_hash: str | None = None

    @property
    def error(self) -> str | None:
        if isinstance(self.payload, dict):
            value = self.payload.get("analysis_error")
            return str(value) if value else None
        return None

    @property
    def status(self) -> str:
        return "error" if self.error else "ok"


@dataclass
class _AnalysisResult:
    decision: QualityDecision
    stages: list[_StageResult] = field(default_factory=list)

    @property
    def run_status(self) -> str:
        """'degraded' when a stage failed but the pipeline carried on.

        The gate deliberately fails open, so a degraded run still produces a
        usable verdict. Recording the distinction is what keeps that from
        looking like a clean success.
        """
        return "degraded" if any(s.status == "error" for s in self.stages) else "succeeded"


def _timed(work: Callable[[], dict[str, Any]]) -> tuple[dict[str, Any], int]:
    started = time.perf_counter()
    payload = work()
    return payload, int((time.perf_counter() - started) * 1000)


def run_meal_analysis(content: bytes) -> _AnalysisResult:
    """Run the pipeline. Holds no database connection.

    Both stages honour the same contract as before: they capture their own
    failures in the payload and never raise, so a degraded stage cannot take
    the upload down with it.
    """
    technical, technical_ms = _timed(lambda: analyze_image_quality(content))
    vision, vision_ms = _timed(lambda: run_image_quality_graph(content))

    stages = [
        _StageResult(
            stage="technical_quality",
            payload=technical,
            latency_ms=technical_ms,
            config_hash=analyzer_config_hash(),
        ),
        _StageResult(
            stage="vision_quality",
            payload=vision,
            latency_ms=vision_ms,
            model_id=MODEL,
            prompt_version=PROMPT_VERSION,
        ),
    ]

    # evaluate_quality() still takes the {"technical": ..., "vision": ...}
    # shape it always took. The two payloads are now separate artifacts in the
    # database, but the gating function -- and its 18 tests -- are untouched.
    decision = evaluate_quality({"technical": technical, "vision": vision})
    return _AnalysisResult(decision=decision, stages=stages)


# ---------------------------------------------------------------------------
# Response mapping
# ---------------------------------------------------------------------------


def _image_asset_kwargs(asset: ImageAsset) -> dict[str, Any]:
    return {
        "role": asset.role,
        "object_key": asset.object_key,
        "content_type": asset.content_type,
        "image_format": asset.image_format,
        "byte_size": asset.byte_size,
        "width": asset.width,
        "height": asset.height,
        "sha256": asset.sha256,
    }


def _to_public(row: MealListRow) -> MealPublic:
    """Explicit field mapping, never MealPublic(**row).

    The API contract and the view are allowed to diverge; spelling out the
    translation is what makes that a decision instead of an accident.
    """
    image_url, thumbnail_url = meal_image_paths(
        row.meal_id,
        has_original=row.has_original,
        has_thumbnail=row.has_thumbnail,
    )
    return MealPublic(
        meal_id=row.meal_id,
        image_url=image_url,
        thumbnail_url=thumbnail_url,
        source=row.source,
        status=row.status,
        created_at=row.created_at,
        processed_at=row.processed_at,
        rejection_reason=row.rejection_reason,
        image_format=row.image_format,
        nutrition_ready=row.nutrition_ready,
        likely_meal_type=row.likely_meal_type,
    )


def _to_detail(row: MealDetailRow) -> MealDetail:
    base = _to_public(row)
    return MealDetail(
        **base.model_dump(),
        width=row.width,
        height=row.height,
        nutrition_blocked_reason=row.nutrition_blocked_reason,
        usability_status=row.usability_status,
        recommended_action=row.recommended_action,
        is_food_image=row.is_food_image,
        food_confidence=row.food_confidence,
        analysis_complete=row.analysis_complete,
        meal_time_source=row.meal_time_source,
        foods=[MealFood(**food) for food in row.foods],
    )


# ---------------------------------------------------------------------------
# The upload
# ---------------------------------------------------------------------------


def create_meal_with_metadata(
    user_id: int,
    source: str,
    metadata: dict[str, Any],
    content: bytes,
    content_type: str,
    filename: str | None,
) -> MealUploadResponse:
    # Checked before anything is written, so a misconfigured deployment fails
    # without leaving half-created meals behind.
    if not is_r2_configured():
        raise RuntimeError(
            "Cloudflare R2 is not configured. Set R2_ACCOUNT_ID, "
            "R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, and R2_BUCKET_NAME."
        )

    captured_at_local = _parse_exif_datetime(
        metadata.get("datetime_original") or metadata.get("datetime")
    )

    # --- T1: claim a meal_id. The R2 object key embeds it. ------------------
    with tx() as cur:
        meal_id = meals_repo.insert_meal(
            cur,
            user_id=user_id,
            source=source,
            captured_at_local=captured_at_local,
        )

    # --- R2. No transaction, no connection held. ---------------------------
    try:
        assets = upload_meal_images(user_id, meal_id, content, content_type, filename)
    except Exception as exc:
        # Record the failure instead of vanishing. Without this the meal would
        # sit at 'pending' forever, which reads as "still analysing".
        with tx() as cur:
            meals_repo.mark_failed(cur, meal_id, str(exc))
        raise

    # --- T2: the bytes exist, so the rows that assert they exist can too. --
    with tx() as cur:
        images_repo.insert_image(
            cur, meal_id=meal_id, **_image_asset_kwargs(assets.original)
        )
        if assets.thumbnail is not None:
            images_repo.insert_image(
                cur, meal_id=meal_id, **_image_asset_kwargs(assets.thumbnail)
            )
        images_repo.insert_exif(
            cur,
            meal_id=meal_id,
            has_exif=bool(metadata.get("has_exif")),
            exif=_exif_for_storage(metadata),
        )
        meals_repo.mark_stored(cur, meal_id)

    # --- OpenCV + Claude. No transaction, no connection held. --------------
    analysis = run_meal_analysis(content)

    # --- T3: the whole run, atomically. ------------------------------------
    with tx() as cur:
        run_id = analysis_repo.start_run(
            cur, meal_id=meal_id, pipeline_version=PIPELINE_VERSION, trigger="upload"
        )
        for stage in analysis.stages:
            analysis_repo.insert_artifact(
                cur,
                run_id=run_id,
                meal_id=meal_id,
                stage=stage.stage,
                status=stage.status,
                payload=stage.payload,
                error_code=stage.error[:200] if stage.error else None,
                model_id=stage.model_id,
                prompt_version=stage.prompt_version,
                config_hash=stage.config_hash,
                latency_ms=stage.latency_ms,
            )
        analysis_repo.insert_verdict(
            cur,
            run_id=run_id,
            meal_id=meal_id,
            decision=analysis.decision,
            rules_version=DECISION_RULES_VERSION,
        )
        analysis_repo.finish_run(cur, run_id=run_id, status=analysis.run_status)

    # Read the response back through the view, so the upload response and the
    # Log list can never disagree about a meal's status.
    with tx() as cur:
        row = meals_repo.get_detail(cur, user_id=user_id, meal_id=meal_id)
    if row is None:  # pragma: no cover - the meal was just committed
        raise RuntimeError(f"meal {meal_id} disappeared after commit")

    public = _to_public(row)
    return MealUploadResponse(
        meal_id=public.meal_id,
        status=public.status,
        image_url=public.image_url,
        thumbnail_url=public.thumbnail_url,
        metadata=metadata,
        message=analysis.decision.message,
        nutrition_ready=public.nutrition_ready,
    )


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------


def list_meals_for_user(
    user_id: int, *, limit: int = 100, before: datetime | None = None
) -> list[MealPublic]:
    with tx() as cur:
        rows = meals_repo.list_for_user(cur, user_id, limit=limit, before=before)
    return [_to_public(row) for row in rows]


def get_meal_for_user(user_id: int, meal_id: int) -> MealDetail | None:
    with tx() as cur:
        row = meals_repo.get_detail(cur, user_id=user_id, meal_id=meal_id)
    return _to_detail(row) if row else None


def get_meal_image_ref(user_id: int, meal_id: int, role: str):
    """The object key and content type for one variant, ownership enforced.

    ``role`` is a bound parameter now. The old version looked the variant up
    in a dict of column names and interpolated the result into the SELECT.
    """
    with tx() as cur:
        return images_repo.get_object_ref(
            cur, user_id=user_id, meal_id=meal_id, role=role
        )
