from graph.builder import build_quality_context
import httpx
import anthropic

from graph import nodes
from graph.nodes import normalize_visible_foods
from graph.schema import VISIBLE_FOODS_SCHEMA


def test_normalizes_aliases_and_deduplicates_visible_foods():
    payload = normalize_visible_foods({
        "result": "identified",
        "visible_foods": [
            {"label": "Jollof Rice", "possible_types": ["Jollof rice", "jollof rice"], "possible_preparations": [], "confidence": 0.78},
            {"label": "rice", "possible_types": [], "possible_preparations": [], "confidence": 0.5},
        ],
        "uncertainties": [],
    })
    assert payload == {"result": "identified", "visible_foods": [{"label": "rice", "possible_types": ["jollof rice"], "possible_preparations": [], "confidence": 0.78}], "uncertainties": []}


def test_unavailable_requires_a_reason_and_invalid_confidence_is_rejected():
    assert normalize_visible_foods({"result": "unavailable", "visible_foods": [], "uncertainties": []}) is None
    assert normalize_visible_foods({"result": "identified", "visible_foods": [{"label": "rice", "possible_types": [], "possible_preparations": [], "confidence": 2}], "uncertainties": []}) is None


def test_quality_context_excludes_food_detection_and_only_tripped_technical_checks():
    context = build_quality_context(
        {"blur": {"issue": True}, "brightness": {"issue": False}},
        {"food_detection": {"is_food_image": True, "food_confidence": 99}, "visibility": {"plate_visible": {"value": True}, "cropped_food": {"value": False}}, "recommended_action": "accept"},
    )
    assert "food_detection" not in context
    assert context["plate_visible"] is True
    assert context["technical_caveats"] == {"blur": {"issue": True}}


def test_visible_foods_persists_safe_provider_error_details(monkeypatch):
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    response = httpx.Response(400, headers={"request-id": "req_m1_schema"}, request=request)
    error = anthropic.BadRequestError(
        "invalid request",
        response=response,
        body={"error": {"type": "invalid_request_error", "message": "schema rejected"}},
    )

    class FailingMessages:
        def create(self, **_kwargs):
            raise error

    class FailingClient:
        messages = FailingMessages()

    monkeypatch.setattr(nodes, "_client", lambda: FailingClient())
    result = nodes.visual_understanding_node(
        {"image_b64": "data", "media_type": "image/jpeg", "quality_context": {}}
    )

    assert result == {"visible_foods": {
        "analysis_error": "upstream_error",
        "provider_error": {
            "exception_type": "BadRequestError",
            "status_code": 400,
            "request_id": "req_m1_schema",
            "provider_error_type": "invalid_request_error",
            "provider_message": "schema rejected",
        },
    }}


def test_visible_foods_schema_avoids_anthropic_unsupported_bounds():
    """Length and numeric bounds are enforced by normalize_visible_foods()."""
    forbidden = {"maxItems", "minItems", "minLength", "maxLength", "minimum", "maximum"}

    def keywords(value):
        if isinstance(value, dict):
            yield from value
            for child in value.values():
                yield from keywords(child)
        elif isinstance(value, list):
            for child in value:
                yield from keywords(child)

    assert forbidden.isdisjoint(keywords(VISIBLE_FOODS_SCHEMA))
