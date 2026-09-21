"""Tests for the quality gate — app/quality_decision.py.

evaluate_quality() is the only thing standing between a garbage photo and the
rest of the pipeline, and it is pure (dict in, dataclass out), so it is the
natural first test target in the codebase.

These tests assert CURRENT behaviour, including the fail-open cases at the
bottom, which are deliberate but worth having pinned down before downstream
stages start depending on them.
"""

from __future__ import annotations

import pytest

from quality_decision import (
    _LOW_QUALITY_MESSAGE,
    _NOT_FOOD_MESSAGE,
    _TECHNICAL_MESSAGES,
    NUTRITION_BLOCK_NOT_FOOD,
    NUTRITION_BLOCK_PHOTO_REJECTED,
    NUTRITION_BLOCK_VISION_UNAVAILABLE,
    evaluate_quality,
)


# --------------------------------------------------------------------------
# Fixtures / builders
# --------------------------------------------------------------------------

def technical(**failing: bool) -> dict:
    """A technical payload shaped like analyze_image_quality()'s output.

    Every check defaults to passing; name a check to make it fail:
        technical(blur=True)
    """
    checks = {"blur", "brightness", "overexposure", "underexposure", "resolution"}
    unknown = set(failing) - checks
    assert not unknown, f"unknown technical check(s): {unknown}"

    payload = {name: {"issue": failing.get(name, False)} for name in checks}
    payload["has_issues"] = any(failing.values())
    return payload


def vision(
    is_food: bool | None = True,
    confidence: object = 90,
    action: str | None = "accept",
) -> dict:
    """A vision payload shaped like image_quality_node()'s output."""
    payload: dict = {}
    if is_food is not None or confidence is not None:
        payload["food_detection"] = {
            "is_food_image": is_food,
            "food_confidence": confidence,
        }
    if action is not None:
        payload["recommended_action"] = action
    return payload


# --------------------------------------------------------------------------
# The happy path
# --------------------------------------------------------------------------

def test_clean_photo_is_accepted():
    decision = evaluate_quality({"technical": technical(), "vision": vision()})

    assert decision.accepted is True
    assert decision.usability_status == "usable"
    assert decision.message is None
    assert decision.is_food_image is True
    assert decision.recommended_action == "accept"


@pytest.mark.parametrize(
    "action",
    ["accept", "continue_with_high_confidence", "continue_with_medium_confidence"],
)
def test_non_rejecting_actions_pass_through(action):
    """Only 'reject' and 'request_retake' should block a photo."""
    decision = evaluate_quality(
        {"technical": technical(), "vision": vision(action=action)}
    )

    assert decision.accepted is True
    assert decision.recommended_action == action


# --------------------------------------------------------------------------
# Not-food short-circuits everything else
# --------------------------------------------------------------------------

def test_not_food_is_rejected():
    decision = evaluate_quality(
        {"technical": technical(), "vision": vision(is_food=False, action="reject")}
    )

    assert decision.accepted is False
    assert decision.usability_status == "rejected"
    assert decision.message == _NOT_FOOD_MESSAGE
    assert decision.is_food_image is False


def test_not_food_suppresses_technical_messages():
    """A photo of a wall that is also blurry should say 'not food', once.

    Telling someone to retake a sharper photo of their wall is noise.
    """
    decision = evaluate_quality(
        {
            "technical": technical(blur=True, underexposure=True),
            "vision": vision(is_food=False, action="reject"),
        }
    )

    assert decision.message == _NOT_FOOD_MESSAGE
    assert _TECHNICAL_MESSAGES["blur"] not in (decision.message or "")


# --------------------------------------------------------------------------
# Technical rejections
# --------------------------------------------------------------------------

@pytest.mark.parametrize("check", sorted(_TECHNICAL_MESSAGES))
def test_each_technical_failure_rejects_with_its_own_message(check):
    decision = evaluate_quality(
        {"technical": technical(**{check: True}), "vision": vision()}
    )

    assert decision.accepted is False
    assert decision.usability_status == "rejected"
    assert decision.message == _TECHNICAL_MESSAGES[check]


def test_multiple_technical_failures_are_joined_once_each():
    decision = evaluate_quality(
        {"technical": technical(blur=True, resolution=True), "vision": vision()}
    )

    assert decision.accepted is False
    assert decision.message is not None
    assert _TECHNICAL_MESSAGES["blur"] in decision.message
    assert _TECHNICAL_MESSAGES["resolution"] in decision.message
    # Joined, not duplicated.
    assert decision.message.count(_TECHNICAL_MESSAGES["blur"]) == 1


# --------------------------------------------------------------------------
# Vision routing rejections
# --------------------------------------------------------------------------

@pytest.mark.parametrize("action", ["reject", "request_retake"])
def test_rejecting_actions_are_rejected(action):
    decision = evaluate_quality(
        {"technical": technical(), "vision": vision(action=action)}
    )

    assert decision.accepted is False
    assert decision.message == _LOW_QUALITY_MESSAGE
    assert decision.recommended_action == action


def test_technical_and_vision_failures_both_surface():
    decision = evaluate_quality(
        {"technical": technical(blur=True), "vision": vision(action="request_retake")}
    )

    assert decision.message is not None
    assert _TECHNICAL_MESSAGES["blur"] in decision.message
    assert _LOW_QUALITY_MESSAGE in decision.message


# --------------------------------------------------------------------------
# food_confidence normalisation (0-100 from the model -> 0-1)
# --------------------------------------------------------------------------

@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (0, 0.0),
        (50, 0.5),
        (100, 1.0),
        (92, 0.92),
        (150, 1.0),    # clamped
        (-10, 0.0),    # clamped
    ],
)
def test_food_confidence_is_normalised_and_clamped(raw, expected):
    decision = evaluate_quality({"technical": technical(), "vision": vision(confidence=raw)})

    assert decision.food_confidence == pytest.approx(expected)


@pytest.mark.parametrize("raw", [None, "high", True, False, [], {}])
def test_non_numeric_food_confidence_becomes_none(raw):
    """bool is a subclass of int, so True/False must be rejected explicitly."""
    decision = evaluate_quality({"technical": technical(), "vision": vision(confidence=raw)})

    assert decision.food_confidence is None


# --------------------------------------------------------------------------
# Graceful degradation — the fail-open paths
# --------------------------------------------------------------------------

def test_vision_error_falls_back_to_technical_checks():
    """A dead vision node must not reject every upload."""
    decision = evaluate_quality(
        {"technical": technical(), "vision": {"analysis_error": "connection reset"}}
    )

    assert decision.accepted is True
    assert decision.is_food_image is None
    assert decision.recommended_action is None
    assert decision.food_confidence is None
    # ...but the nutrition gate does not fall back. See the nutrition section.
    assert decision.nutrition_ready is False


def test_vision_error_still_honours_technical_rejection():
    decision = evaluate_quality(
        {
            "technical": technical(blur=True),
            "vision": {"analysis_error": "connection reset"},
        }
    )

    assert decision.accepted is False
    assert decision.message == _TECHNICAL_MESSAGES["blur"]


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"technical": {}, "vision": {}},
        {"technical": None, "vision": None},
        {"technical": ["not", "a", "dict"], "vision": "not a dict"},
        {"technical": technical(), "vision": {"food_detection": "not a dict"}},
    ],
)
def test_malformed_payloads_do_not_raise(payload):
    """Whatever arrives, the gate must return a decision rather than blow up
    the upload transaction."""
    decision = evaluate_quality(payload)

    assert decision.usability_status in {"usable", "rejected"}
    assert isinstance(decision.accepted, bool)


def test_total_analysis_failure_is_stored_but_not_nutrition_ready():
    """Both analyzers dead: keep the photo, refuse to estimate from it.

    There are no reasons to reject, so the storage gate accepts — the user is
    not punished for our outage. But nothing confirmed this is food, so the
    nutrition gate stays shut.
    """
    decision = evaluate_quality(
        {
            "technical": {"analysis_error": "decode failed", "has_issues": False},
            "vision": {"analysis_error": "decode_failed"},
        }
    )

    assert decision.accepted is True
    assert decision.message is None
    assert decision.nutrition_ready is False
    assert decision.analysis_complete is False


# --------------------------------------------------------------------------
# The nutrition gate — fails CLOSED, requires positive evidence
# --------------------------------------------------------------------------

def test_confirmed_food_on_a_clean_photo_is_nutrition_ready():
    decision = evaluate_quality({"technical": technical(), "vision": vision()})

    assert decision.nutrition_ready is True
    assert decision.nutrition_blocked_reason is None
    assert decision.analysis_complete is True


def test_dog_photo_during_vision_outage_is_accepted_but_blocked():
    """The case the two-gate split exists for.

    A sharp, well-lit photo of something that is not food, uploaded while the
    vision node is unavailable. OpenCV has no concept of food, so every
    technical check passes and the storage gate accepts. Nothing ever confirmed
    it was a meal, so nutrition must not proceed.
    """
    decision = evaluate_quality(
        {"technical": technical(), "vision": {"analysis_error": "503 upstream"}}
    )

    assert decision.accepted is True                  # photo kept
    assert decision.is_food_image is None             # never determined
    assert decision.nutrition_ready is False          # but no calories from it
    assert decision.nutrition_blocked_reason == NUTRITION_BLOCK_VISION_UNAVAILABLE


def test_not_food_blocks_nutrition_with_its_own_reason():
    decision = evaluate_quality(
        {"technical": technical(), "vision": vision(is_food=False, action="reject")}
    )

    assert decision.nutrition_ready is False
    assert decision.nutrition_blocked_reason == NUTRITION_BLOCK_NOT_FOOD


@pytest.mark.parametrize(
    "payload",
    [
        {"technical": technical(blur=True), "vision": vision()},
        {"technical": technical(), "vision": vision(action="request_retake")},
    ],
    ids=["technical_failure", "vision_retake"],
)
def test_rejected_food_photos_block_nutrition(payload):
    """Confirmed food, but the photo was rejected — no estimate either way."""
    decision = evaluate_quality(payload)

    assert decision.is_food_image is True
    assert decision.accepted is False
    assert decision.nutrition_ready is False
    assert decision.nutrition_blocked_reason == NUTRITION_BLOCK_PHOTO_REJECTED


def test_nutrition_ready_implies_accepted():
    """The nutrition gate must never be more permissive than the storage gate.

    Swept across the payload space so a future edit to either gate cannot
    quietly invert the relationship.
    """
    payloads = [
        {"technical": technical(**{check: True}), "vision": vision(is_food=food, action=action)}
        for check in ["blur", "brightness", "overexposure", "underexposure", "resolution"]
        for food in [True, False, None]
        for action in ["accept", "reject", "request_retake", None]
    ] + [
        {"technical": technical(), "vision": vision(is_food=food, action=action)}
        for food in [True, False, None]
        for action in ["accept", "continue_with_high_confidence", "reject", None]
    ]

    for payload in payloads:
        decision = evaluate_quality(payload)
        if decision.nutrition_ready:
            assert decision.accepted, f"nutrition_ready but not accepted: {payload}"
            assert decision.is_food_image is True, f"nutrition_ready without food: {payload}"
            assert decision.nutrition_blocked_reason is None


def test_missing_technical_still_allows_nutrition_when_food_confirmed():
    """OpenCV dying should not block estimation on its own.

    The vision node covers usability via recommended_action, and it is the only
    stage that can confirm food. Missing technical checks are reflected in
    analysis_complete so downstream can discount confidence.
    """
    decision = evaluate_quality(
        {"technical": {"analysis_error": "cv2 decode failed"}, "vision": vision()}
    )

    assert decision.nutrition_ready is True
    assert decision.analysis_complete is False
