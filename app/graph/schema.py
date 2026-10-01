from __future__ import annotations

from typing import Any

# Structured-output contract for the image-quality node. Claude is constrained
# to emit exactly this shape (output_config.format), so the node never has to
# defensively parse free-form text.

SEVERITY = {"type": "string", "enum": ["none", "low", "medium", "high"]}
LEVEL = {"type": "string", "enum": ["none", "low", "medium", "high"]}


def _signal(value_schema: dict[str, Any]) -> dict[str, Any]:
    """A judged signal: the call, how sure the model is, and how much it hurts
    downstream calorie/macro estimation."""
    return {
        "type": "object",
        "properties": {
            "value": value_schema,
            "confidence": {"type": "number"},
            "severity": SEVERITY,
        },
        "required": ["value", "confidence", "severity"],
        "additionalProperties": False,
    }


_BOOL = {"type": "boolean"}

# Allowed values for the overall routing decision the node recommends.
RECOMMENDED_ACTIONS = [
    "accept",
    "continue_with_high_confidence",
    "continue_with_medium_confidence",
    "request_retake",
    "reject",
]

DETECTED_ISSUES_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "food_detection": {
            "type": "object",
            "properties": {
                "is_food_image": {"type": "boolean"},
                # 0-100 confidence that the image actually shows food.
                "food_confidence": {"type": "integer"},
            },
            "required": ["is_food_image", "food_confidence"],
            "additionalProperties": False,
        },
        "visibility": {
            "type": "object",
            "properties": {
                "plate_visible": _signal(_BOOL),
                "cropped_food": _signal(_BOOL),
            },
            "required": ["plate_visible", "cropped_food"],
            "additionalProperties": False,
        },
        "geometry": {
            "type": "object",
            "properties": {
                "bad_angle": _signal(_BOOL),
                "depth_unclear": _signal(_BOOL),
            },
            "required": ["bad_angle", "depth_unclear"],
            "additionalProperties": False,
        },
        "occlusion": {
            "type": "object",
            "properties": {
                "food_overlap_level": _signal(LEVEL),
                "sauce_hiding_food": _signal(_BOOL),
            },
            "required": ["food_overlap_level", "sauce_hiding_food"],
            "additionalProperties": False,
        },
        "portion_estimation": {
            "type": "object",
            "properties": {
                "portion_difficulty": {
                    "type": "object",
                    "properties": {
                        "value": LEVEL,
                        "confidence": {"type": "number"},
                        "reasons": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["value", "confidence", "reasons"],
                    "additionalProperties": False,
                },
            },
            "required": ["portion_difficulty"],
            "additionalProperties": False,
        },
        "recommended_action": {"type": "string", "enum": RECOMMENDED_ACTIONS},
    },
    "required": [
        "food_detection",
        "visibility",
        "geometry",
        "occlusion",
        "portion_estimation",
        "recommended_action",
    ],
    "additionalProperties": False,
}

SYSTEM_PROMPT = """You are the image-quality stage of a meal-photo analysis \
pipeline whose downstream job is estimating calories and macronutrients.

Judge how usable a single meal photo is for that downstream estimation. For \
each signal, return whether it applies, your confidence (0.0-1.0), and a \
severity describing how much it would harm calorie/macro estimation \
(none/low/medium/high). For food_detection.food_confidence, use an integer \
0-100.

Definitions:
- visibility.plate_visible: is the plate/container the food sits in visible \
(useful as a scale reference)?
- visibility.cropped_food: is food cut off by the frame edges?
- geometry.bad_angle: is the camera angle poor for judging portion size \
(e.g. extreme side-on)?
- geometry.depth_unclear: is it hard to judge the height/volume of the food?
- occlusion.food_overlap_level: how much food is hidden behind other food?
- occlusion.sauce_hiding_food: is sauce/topping obscuring the actual food?
- portion_estimation.portion_difficulty: overall difficulty of estimating \
portion size, with short free-text reasons.
- recommended_action: the routing decision for this photo.

Be reasonable, not overly strict: a normal, slightly imperfect phone photo of \
a meal should still be usable."""

# M1's authoritative, lossless visible-food contract. Keep this separate from
# the quality prompt: a change to one must not accidentally alter the other
# stage's provenance. Anthropic structured outputs rejects JSON Schema bounds
# such as maxItems/minimum; normalize_visible_foods() enforces those limits
# after parsing instead.
VISIBLE_FOODS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "result": {"type": "string", "enum": ["identified", "unavailable"]},
        "visible_foods": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "label": {"type": "string"},
                    "possible_types": {"type": "array", "items": {"type": "string"}},
                    "possible_preparations": {"type": "array", "items": {"type": "string"}},
                    "confidence": {"type": "number"},
                },
                "required": ["label", "possible_types", "possible_preparations", "confidence"],
                "additionalProperties": False,
            },
        },
        "uncertainties": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["result", "visible_foods", "uncertainties"],
    "additionalProperties": False,
}

VISIBLE_FOODS_PROMPT = """You identify only foods visibly supported by a single meal photo.
Return coarse, lowercase, singular food-category labels (for example rice, chicken,
plantain), merging repeated portions of the same category. Do not infer hidden
ingredients, portions, nutrition, regions, masks, or bounding boxes. Put dish or
subtype hypotheses in possible_types and cooking methods in possible_preparations.
Use alternatives only for genuine ambiguity. If foods cannot be responsibly
identified, return result unavailable, no visible_foods, and concise uncertainty.
Quality context is a limitation, never evidence that a food exists."""
