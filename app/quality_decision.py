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


@dataclass
class QualityDecision:
    accepted: bool
    usability_status: str            # "usable" | "rejected"
    recommended_action: str | None   # echoed from the vision node when present
    is_food_image: bool | None       # for image_qualities.is_food_image
    food_confidence: float | None    # normalized 0-1 for image_qualities.food_confidence
    message: str | None              # user-facing; set only when rejected


def _normalize_confidence(value: Any) -> float | None:
    """Vision reports food_confidence as an int 0-100; the DB column is 0-1."""
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return None
    return max(0.0, min(1.0, value / 100.0))


def evaluate_quality(detected_issues: dict[str, Any]) -> QualityDecision:
    """Decide whether an uploaded meal photo is usable.

    Combines the deterministic technical checks with the vision node's
    is_food_image / recommended_action. Designed to fail gracefully: if the
    vision node erred (no is_food_image / recommended_action), the decision
    falls back to the technical checks alone rather than rejecting outright.
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

    # Not food is the most decisive failure — surface only that message.
    if is_food_image is False:
        return QualityDecision(
            accepted=False,
            usability_status="rejected",
            recommended_action=recommended_action,
            is_food_image=False,
            food_confidence=food_confidence,
            message=_NOT_FOOD_MESSAGE,
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

    return QualityDecision(
        accepted=accepted,
        usability_status="usable" if accepted else "rejected",
        recommended_action=recommended_action,
        is_food_image=is_food_image,
        food_confidence=food_confidence,
        message=message,
    )
