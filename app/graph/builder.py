from __future__ import annotations

import base64
import io
from functools import lru_cache
from typing import Any

from langgraph.graph import END, START, StateGraph
from PIL import Image

from graph.nodes import image_quality_node
from graph.state import ImageQualityState

try:
    import pillow_heif

    pillow_heif.register_heif_opener()
except ImportError:
    pass

# Longest edge (px) we send to the model. The standard vision tier is ~1568px;
# quality assessment doesn't need more, and downscaling caps image-token cost.
MAX_EDGE = 1568


@lru_cache(maxsize=1)
def build_image_quality_graph():
    """Compile the image-analysis graph once and reuse it.

    A single image-quality node for now; future stages (food identification,
    portion sizing, calorie/macro estimation) become additional nodes and edges
    on this same graph.
    """
    builder = StateGraph(ImageQualityState)
    builder.add_node("image_quality", image_quality_node)
    builder.add_edge(START, "image_quality")
    builder.add_edge("image_quality", END)
    return builder.compile()


def _to_jpeg_b64(content: bytes) -> str:
    """Decode any supported upload (incl. HEIC) and re-encode as a downscaled
    JPEG, so the model always receives a supported, reasonably-sized image."""
    with Image.open(io.BytesIO(content)) as img:
        img = img.convert("RGB")
        img.thumbnail((MAX_EDGE, MAX_EDGE))
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85)
    return base64.standard_b64encode(buf.getvalue()).decode("ascii")


def run_image_quality_graph(content: bytes) -> dict[str, Any]:
    """Run the graph on raw image bytes and return the detected_issues payload.

    Returns an ``analysis_error`` payload (never raises) if the image can't be
    decoded, so callers can persist the result unconditionally.
    """
    try:
        image_b64 = _to_jpeg_b64(content)
    except Exception as exc:
        return {"analysis_error": f"decode_failed: {exc}"}

    result = build_image_quality_graph().invoke(
        {"image_b64": image_b64, "media_type": "image/jpeg"}
    )
    return result.get("detected_issues", {"analysis_error": "no_result"})
