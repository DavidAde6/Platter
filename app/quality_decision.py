from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# User-facing, actionable messages for each deterministic (OpenCV) technical
# failure. Keys match analyze_image_quality()'s detected_issues structure.
_TECHNICAL_MESSAGES: dict[str, str] = {
    "blur": "The photo looks too blurry. Try retaking it in focus.",
    "underexposure": "The photo is too dark. Try retaking it with more light.",
    "overexposure": "The photo is too bright. Try retaking it with less glare.",
    "brightness": "The lighting makes the meal hard to see. Try even, natural light.",
    "resolution": "The photo's resolution is too low. Upload a larger, clearer image.",
}

# Vision recommended_action values that mean "don't accept this photo as-is".
_REJECTING_ACTIONS = {"reject", "request_retake"}

_NOT_FOOD_MESSAGE = (
    "We couldn't find a meal in this photo. Please upload a clear photo of your food."
)
_LOW_QUALITY_MESSAGE = (
    "This photo isn't clear enough to analyze your meal. Please try another photo."
)

# Why nutrition estimation is not permitted for a meal. Internal values, not
# user-facing copy -- they exist so a blocked meal can be diagnosed and, in the
# vision_unavailable case, retried later.
# Bump when the gating logic or any user-facing message changes. Stored on
# every verdict so a rules change is visible in the data instead of making
# old and new verdicts silently incomparable.
DECISION_RULES_VERSION = "gate/2026-09-12.1"

NUTRITION_BLOCK_NOT_FOOD = "not_food"
NUTRITION_BLOCK_VISION_UNAVAILABLE = "vision_unavailable"
NUTRITION_BLOCK_PHOTO_REJECTED = "photo_rejected"


@dataclass
class QualityDecision:
    """The outcome of two separate gates with opposite failure preferences.

    STORAGE GATE (``accepted``) FAILS OPEN. When analysis is unavailable we
    keep the photo and let the user move on. Rejecting every upload during an
    Anthropic outage would tell users "this photo isn't clear enough", which is
    false, unactionable, and looks like the product is broken.

    NUTRITION GATE (``nutrition_ready``) FAILS CLOSED. It requires positive
    evidence -- is_food_image is True -- rather than merely the absence of a
    reason to reject. Without this, a photo of a dog passes during a vision
    outage, because the OpenCV checks only measure blur, brightness and
    resolution and have no concept of food. Attaching a calorie number to that
    is worse than attaching nothing.
    """

    # --- storage gate: fails OPEN ---
    accepted: bool
    usability_status: str            # "usable" | "rejected"
    recommended_action: str | None   # echoed from the vision node when present
    is_food_image: bool | None       # persisted to image_qualities.is_food_image
    # Normalized 0-1 (the model reports 0-100). Downstream confidence weighting
    # (AnalysisPipeline.md "Fusion") wants the normalized form. Persisted into
    # detected_issues["decision"] by meals.py.
    food_confidence: float | None
    message: str | None              # user-facing; set only when rejected

    # --- nutrition gate: fails CLOSED ---
    # True only when this meal has confirmed food and may receive a nutrition
    # estimate. Every consumer downstream of the gate must branch on this, not
    # on `accepted`.
    nutrition_ready: bool
    # One of the NUTRITION_BLOCK_* constants, or None when nutrition_ready.
    nutrition_blocked_reason: str | None
    # Did both analyzers actually produce results? False means some signals are
    # missing rather than clean, so downstream confidence should be discounted
    # even when nutrition_ready is True.
    analysis_complete: bool


def _normalize_confidence(value: Any) -> float | None:
    """Vision reports food_confidence as an int 0-100; the DB column is 0-1."""
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return None
    return max(0.0, min(1.0, value / 100.0))


def _ran(payload: Any) -> bool:
    """Did an analyzer actually produce results?

    A failed stage returns {"analysis_error": ...}, which contributes no
    rejection reasons -- so "checked and found nothing wrong" and "never ran"
    are indistinguishable to the reject logic unless asked directly.
    """
    return isinstance(payload, dict) and bool(payload) and "analysis_error" not in payload


def evaluate_quality(detected_issues: dict[str, Any]) -> QualityDecision:
    """Decide whether an uploaded meal photo is usable, and separately whether
    it may receive a nutrition estimate.

    Combines the deterministic technical checks with the vision node's
    is_food_image / recommended_action.

    The storage decision fails gracefully: if the vision node erred (no
    is_food_image / recommended_action), it falls back to the technical checks
    alone rather than rejecting outright. The nutrition decision does not --
    see QualityDecision for why the two differ.
    """
    technical = detected_issues.get("technical") or {}
    vision = detected_issues.get("vision") or {}

    food = vision.get("food_detection") if isinstance(vision, dict) else None
    is_food_image = food.get("is_food_image") if isinstance(food, dict) else None
    food_confidence = (
        _normalize_confidence(food.get("food_confidence"))
        if isinstance(food, dict)
        else None
    )
    recommended_action = (
        vision.get("recommended_action") if isinstance(vision, dict) else None
    )

    # Did each stage actually run? vision_ran is inferred from its outputs
    # rather than the payload shape, since a schema-valid response that somehow
    # carried neither field is just as unusable as an explicit error.
    technical_ran = _ran(technical)
    vision_ran = is_food_image is not None or recommended_action is not None
    analysis_complete = technical_ran and vision_ran

    # Not food is the most decisive failure — surface only that message.
    if is_food_image is False:
        return QualityDecision(
            accepted=False,
            usability_status="rejected",
            recommended_action=recommended_action,
            is_food_image=False,
            food_confidence=food_confidence,
            message=_NOT_FOOD_MESSAGE,
            nutrition_ready=False,
            nutrition_blocked_reason=NUTRITION_BLOCK_NOT_FOOD,
            analysis_complete=analysis_complete,
        )

    reasons: list[str] = []

    # Deterministic technical failures (thresholds are already lenient, so a
    # tripped check means the photo is genuinely unusable).
    if isinstance(technical, dict):
        for key, message in _TECHNICAL_MESSAGES.items():
            check = technical.get(key)
            if isinstance(check, dict) and check.get("issue"):
                reasons.append(message)

    # Vision's overall routing decision.
    if recommended_action in _REJECTING_ACTIONS:
        reasons.append(_LOW_QUALITY_MESSAGE)

    accepted = not reasons
    # Dedupe while preserving order, then join into one message.
    message = None if accepted else " ".join(dict.fromkeys(reasons))

    # The nutrition gate. Note the asymmetry with `accepted` above: that is
    # "no reason to reject", this is "positive reason to proceed". is_food_image
    # is None whenever the vision node was unavailable, and `is not True`
    # deliberately catches it.
    if is_food_image is not True:
        nutrition_ready = False
        nutrition_blocked_reason = NUTRITION_BLOCK_VISION_UNAVAILABLE
    elif not accepted:
        nutrition_ready = False
        nutrition_blocked_reason = NUTRITION_BLOCK_PHOTO_REJECTED
    else:
        nutrition_ready = True
        nutrition_blocked_reason = None

    return QualityDecision(
        accepted=accepted,
        usability_status="usable" if accepted else "rejected",
        recommended_action=recommended_action,
        is_food_image=is_food_image,
        food_confidence=food_confidence,
        message=message,
        nutrition_ready=nutrition_ready,
        nutrition_blocked_reason=nutrition_blocked_reason,
        analysis_complete=analysis_complete,
    )
