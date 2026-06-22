from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

import anthropic

from graph.schema import DETECTED_ISSUES_SCHEMA, SYSTEM_PROMPT
from graph.state import ImageQualityState

# Vision-capable model. Opus 4.8 supports both image input and structured
# outputs (output_config.format), so the node gets schema-valid JSON back.
MODEL = "claude-opus-4-8"


@lru_cache(maxsize=1)
def _client() -> anthropic.Anthropic:
    # Reads ANTHROPIC_API_KEY from the environment, like the other services.
    # Created lazily and cached so importing the graph never needs a key.
    return anthropic.Anthropic()


def image_quality_node(state: ImageQualityState) -> dict[str, Any]:
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
        return {"detected_issues": {"analysis_error": str(exc)}}
