from __future__ import annotations

import base64
import io
from functools import lru_cache
from typing import Any

from langgraph.graph import END, START, StateGraph
from PIL import Image

from graph.nodes import image_quality_node, visual_understanding_node
from graph.state import MealAnalysisState
from quality_decision import evaluate_quality

try:
    import pillow_heif

    pillow_heif.register_heif_opener()
except ImportError:
    pass

# Longest edge (px) we send to the model. The standard vision tier is ~1568px;
# quality assessment doesn't need more, and downscaling caps image-token cost.
MAX_EDGE = 1568

# Which assembly of stages the graph currently represents. Recorded on
# analysis_runs so runs from different graph shapes stay comparable.
# Bump when a node or edge is added, removed or reordered.
PIPELINE_VERSION = "m1-visible-foods"


@lru_cache(maxsize=1)
def build_meal_analysis_graph():
    """Compile the image-analysis graph once and reuse it.

    A single image-quality node for now; future stages (food identification,
    portion sizing, calorie/macro estimation) become additional nodes and edges
    on this same graph.
    """
    builder = StateGraph(MealAnalysisState)
    builder.add_node("image_quality", image_quality_node)
    builder.add_edge(START, "image_quality")
    builder.add_edge("image_quality", END)
    return builder.compile()


# Kept for callers that only need the quality graph API.
build_image_quality_graph = build_meal_analysis_graph


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

    result = build_meal_analysis_graph().invoke(
        {"image_b64": image_b64, "media_type": "image/jpeg"}
    )
    return result.get("detected_issues", {"analysis_error": "no_result"})


def build_quality_context(technical: dict[str, Any], vision: dict[str, Any]) -> dict[str, Any]:
    """Distil only limitations relevant to visible-food identification.

    The gate's food detection fields intentionally never appear: they decided
    routing, and are not evidence for a particular food label.
    """
    context: dict[str, Any] = {}
    paths = {
        "plate_visible": ("visibility", "plate_visible"),
        "cropped_food": ("visibility", "cropped_food"),
        "bad_angle": ("geometry", "bad_angle"),
        "depth_unclear": ("geometry", "depth_unclear"),
        "food_overlap_level": ("occlusion", "food_overlap_level"),
        "sauce_hiding_food": ("occlusion", "sauce_hiding_food"),
        "portion_difficulty": ("portion_estimation", "portion_difficulty"),
    }
    for name, (section, key) in paths.items():
        value = vision.get(section, {}).get(key) if isinstance(vision, dict) else None
        if isinstance(value, dict) and "value" in value:
            context[name] = value["value"]
    action = vision.get("recommended_action") if isinstance(vision, dict) else None
    if action:
        context["recommended_action"] = action
    # Technical checks only constrain the visual call when they actually
    # tripped. Keep payload names and values for operator traceability.
    checks = technical.get("checks", technical) if isinstance(technical, dict) else {}
    if isinstance(checks, dict):
        tripped = {key: value for key, value in checks.items() if isinstance(value, dict) and value.get("issue") is True}
        if tripped:
            context["technical_caveats"] = tripped
    return context


def run_meal_analysis_graph(content: bytes, technical_quality: dict[str, Any]) -> dict[str, Any]:
    """Normalize once, then run quality and conditionally visible-foods."""
    try:
        image_b64 = _to_jpeg_b64(content)
    except Exception:
        error = {"analysis_error": "decode_failed"}
        return {"vision_quality": error, "visible_foods": error, "quality_context": None}
    result = build_meal_analysis_graph().invoke({"image_b64": image_b64, "media_type": "image/jpeg"})
    vision = result.get("detected_issues", {"analysis_error": "no_result"})
    decision = evaluate_quality({"technical": technical_quality, "vision": vision})
    if not decision.accepted:
        return {"vision_quality": vision, "visible_foods": {"reason": "photo_rejected"}, "quality_context": None}
    context = build_quality_context(technical_quality, vision)
    visible = visual_understanding_node({"image_b64": image_b64, "media_type": "image/jpeg", "quality_context": context}).get("visible_foods", {"analysis_error": "no_result"})
    return {"vision_quality": vision, "visible_foods": visible, "quality_context": context}
