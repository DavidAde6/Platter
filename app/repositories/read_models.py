"""Typed rows for the read views.

One model per view, with fields non-Optional wherever the view guarantees NOT
NULL. That is deliberate and it is the point: a renamed, dropped or retyped
view column becomes a ``ValidationError`` at the boundary instead of a silent
``None`` three layers later.

The old code had exactly that failure mode -- ``resolve_meal_urls()`` probed
``meal.get("image_url")``, so a changed projection produced meals with no
images and no error anywhere.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class MealListRow(BaseModel):
    """A row of v_meal_list."""

    # From meals; all NOT NULL there.
    meal_id: int
    user_id: int
    source: str
    created_at: datetime
    lifecycle: str

    # Derived in the view and therefore never null: status is a CASE with an
    # ELSE, nutrition_ready is COALESCEd, the has_* flags are IS NOT NULL
    # tests, and both time fields fall back rather than returning null.
    status: str
    nutrition_ready: bool
    has_original: bool
    has_thumbnail: bool
    likely_meal_type: str
    meal_time_source: str

    # Legitimately absent: no image row yet, or no verdict yet.
    image_format: str | None = None
    width: int | None = None
    height: int | None = None
    nutrition_blocked_reason: str | None = None
    rejection_reason: str | None = None
    processed_at: datetime | None = None


class MealDetailRow(MealListRow):
    """A row of v_meal_detail: the list row plus verdict and foods."""

    # Always present (COALESCE to an empty array), even with no analysis.
    foods: list[dict[str, Any]] = []

    # All absent until a run has produced a verdict.
    run_id: int | None = None
    pipeline_version: str | None = None
    run_status: str | None = None
    usability_status: str | None = None
    recommended_action: str | None = None
    is_food_image: bool | None = None
    food_confidence: float | None = None
    analysis_complete: bool | None = None
    rules_version: str | None = None


class ImageRef(BaseModel):
    """Enough to serve the authenticated image proxy, and nothing more."""

    object_key: str
    content_type: str


class StageStatusRow(BaseModel):
    """A row of v_analysis_stage_status. Debugging surface."""

    stage: str
    status: str
    error_code: str | None = None
    model_id: str | None = None
    prompt_version: str | None = None
    config_hash: str | None = None
    latency_ms: int | None = None
    created_at: datetime
