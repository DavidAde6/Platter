from __future__ import annotations

from typing import Any, TypedDict


class ImageQualityState(TypedDict, total=False):
    """Shared state threaded through the image-analysis graph.

    Inputs are set before invocation; each node reads what it needs and writes
    its result back. Today there is a single image-quality node, but this is the
    backbone for the wider vision pipeline (calorie / macronutrient estimation),
    so new nodes add their own keys here rather than changing the call surface.
    """

    # --- inputs ---
    image_b64: str          # base64-encoded JPEG of the meal photo
    media_type: str         # always "image/jpeg" (re-encoded before invocation)

    # --- outputs ---
    # The image-quality node's analysis, shaped for the image_qualities
    # detected_issues JSONB column.
    detected_issues: dict[str, Any]
