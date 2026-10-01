from __future__ import annotations

import json
import logging
import math
from functools import lru_cache
from typing import Any

import anthropic

from graph.schema import (DETECTED_ISSUES_SCHEMA, SYSTEM_PROMPT, VISIBLE_FOODS_PROMPT,
                          VISIBLE_FOODS_SCHEMA)
from graph.state import MealAnalysisState

# Vision-capable model. Opus 4.8 supports both image input and structured
# outputs (output_config.format), so the node gets schema-valid JSON back.
MODEL = "claude-opus-4-8"

logger = logging.getLogger(__name__)

# Bump on any change to SYSTEM_PROMPT or DETECTED_ISSUES_SCHEMA. Persisted
# with every artifact this node produces, so a stored payload can be traced
# to the prompt that produced it and stale ones can be found and re-run.
PROMPT_VERSION = "quality/2026-09-12.1"
VISIBLE_FOODS_PROMPT_VERSION = "visible-foods/2026-09-30.1"


@lru_cache(maxsize=1)
def _client() -> anthropic.Anthropic:
    # Reads ANTHROPIC_API_KEY from the environment, like the other services.
    # Created lazily and cached so importing the graph never needs a key.
    return anthropic.Anthropic()


def image_quality_node(state: MealAnalysisState) -> dict[str, Any]:
    """Assess a meal photo's usability for calorie/macro estimation.

    Sends the image to Claude and constrains the response to
    DETECTED_ISSUES_SCHEMA. Any failure (missing API key, network, etc.) is
    captured as an ``analysis_error`` rather than raised, so a degraded vision
    stage never breaks the surrounding upload.
    """
    try:
        response = _client().messages.create(
            model=MODEL,
            max_tokens=2048,
            system=SYSTEM_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": state["media_type"],
                                "data": state["image_b64"],
                            },
                        },
                        {
                            "type": "text",
                            "text": "Analyze this meal photo for calorie and "
                            "macronutrient estimation readiness.",
                        },
                    ],
                }
            ],
            output_config={
                "format": {"type": "json_schema", "schema": DETECTED_ISSUES_SCHEMA}
            },
        )

        if response.stop_reason == "refusal":
            return {"detected_issues": {"analysis_error": "model_refusal"}}

        # output_config.format guarantees the first text block is valid JSON
        # matching the schema.
        text = next(b.text for b in response.content if b.type == "text")
        return {"detected_issues": json.loads(text)}
    except Exception as exc:
        return {"detected_issues": {"analysis_error": "upstream_error"}}


def _unique_strings(values: Any, limit: int) -> list[str]:
    result: list[str] = []
    for value in values if isinstance(values, list) else []:
        text = str(value).strip().lower()
        if text and text not in result:
            result.append(text)
        if len(result) == limit:
            break
    return result


# Deliberately a rubric, not a closed enum. Expand it when evaluation outputs
# demonstrate a stable alias rather than rejecting unfamiliar valid foods.
ALIASES = {"grilled chicken": "chicken", "fried chicken": "chicken", "jollof rice": "rice", "fried rice": "rice", "ripe plantains": "plantain", "plantains": "plantain"}


def normalize_visible_foods(payload: Any) -> dict[str, Any] | None:
    if not isinstance(payload, dict) or set(payload) != {"result", "visible_foods", "uncertainties"}:
        return None
    result, foods = payload.get("result"), payload.get("visible_foods")
    uncertainties = _unique_strings(payload.get("uncertainties"), 8)
    if result not in {"identified", "unavailable"} or not isinstance(foods, list) or len(foods) > 12:
        return None
    normalized: list[dict[str, Any]] = []
    for item in foods:
        if not isinstance(item, dict) or set(item) != {"label", "possible_types", "possible_preparations", "confidence"}:
            return None
        label = str(item["label"]).strip().lower()
        confidence = item["confidence"]
        if not label or len(label) > 80 or not isinstance(confidence, (int, float)) or isinstance(confidence, bool) or not math.isfinite(confidence) or not 0 <= confidence <= 1:
            return None
        label = ALIASES.get(label, label)
        if any(food["label"] == label for food in normalized):
            continue
        types = _unique_strings(item["possible_types"], 4)
        preparations = _unique_strings(item["possible_preparations"], 4)
        if not isinstance(item["possible_types"], list) or not isinstance(item["possible_preparations"], list):
            return None
        normalized.append({"label": label, "possible_types": types, "possible_preparations": preparations, "confidence": float(confidence)})
    if (result == "identified" and not normalized) or (result == "unavailable" and (normalized or not uncertainties)):
        return None
    return {"result": result, "visible_foods": normalized, "uncertainties": uncertainties}


def _provider_error_payload(exc: anthropic.APIError) -> dict[str, Any]:
    """Return operator-safe provider diagnostics without exposing them to clients.

    The stable ``analysis_error`` value remains the public pipeline contract.
    The nested data is persisted only in the raw artifact and logged, so an
    HTTP 400 (bad request/schema) can be distinguished from rate limits and
    provider outages after the upload has completed.
    """
    status_code = getattr(exc, "status_code", None)
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", None)
    request_id = headers.get("request-id") if headers else None
    detail: dict[str, Any] = {"exception_type": type(exc).__name__}
    body = getattr(exc, "body", None)
    error = body.get("error") if isinstance(body, dict) else None
    if isinstance(error, dict):
        error_type = error.get("type")
        message = error.get("message")
        if isinstance(error_type, str) and error_type:
            detail["provider_error_type"] = error_type
        # Provider validation messages describe the request, not the image.
        # Bound the value so diagnostics stay useful without becoming a log sink.
        if isinstance(message, str) and message:
            detail["provider_message"] = message[:500]
    if isinstance(status_code, int):
        detail["status_code"] = status_code
    if isinstance(request_id, str) and request_id:
        detail["request_id"] = request_id

    logger.warning("visible_foods_provider_error", extra={"provider_error": detail})
    return {"analysis_error": "upstream_error", "provider_error": detail}


def visual_understanding_node(state: MealAnalysisState) -> dict[str, Any]:
    """Never-raise M1 vision stage with stable, client-safe error codes."""
    try:
        response = _client().messages.create(
            model=MODEL, max_tokens=2048, system=VISIBLE_FOODS_PROMPT,
            messages=[{"role": "user", "content": [
                {"type": "image", "source": {"type": "base64", "media_type": state["media_type"], "data": state["image_b64"]}},
                {"type": "text", "text": "Quality limitations: " + json.dumps(state.get("quality_context", {}))},
            ]}],
            output_config={"format": {"type": "json_schema", "schema": VISIBLE_FOODS_SCHEMA}},
        )
        if response.stop_reason == "refusal":
            return {"visible_foods": {"analysis_error": "model_refusal"}}
        text = next(block.text for block in response.content if block.type == "text")
        normalized = normalize_visible_foods(json.loads(text))
        return {"visible_foods": normalized if normalized else {"analysis_error": "invalid_response"}}
    except (json.JSONDecodeError, StopIteration, KeyError, TypeError):
        return {"visible_foods": {"analysis_error": "invalid_response"}}
    except anthropic.APIError as exc:
        return {"visible_foods": _provider_error_payload(exc)}
    except Exception:
        return {"visible_foods": {"analysis_error": "client_error"}}
