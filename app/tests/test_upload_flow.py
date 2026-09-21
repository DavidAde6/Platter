"""The upload orchestration end to end, against a real (test) database.

R2 and the Anthropic call are monkeypatched -- this suite should not need
real credentials to run in CI -- but every database write is real, through
the actual three-transaction path in meals.py.

Each test pins one of the failure semantics the transaction split exists to
produce. Before this redesign, all four of these went through a single
transaction: a mid-pipeline failure rolled the entire upload back and the
photo was gone with no trace it was ever attempted.
"""

from __future__ import annotations

import io

import pytest
from PIL import Image, ImageDraw

import meals
from storage import ImageAsset, UploadedAssets

pytestmark = pytest.mark.usefixtures("app_db")


def _real_jpeg_bytes() -> bytes:
    """A genuinely decodable image that also clears the technical checks.

    Needed so the happy path exercises technical_quality for real rather than
    hitting one of its own rejection paths. Two failure modes to avoid, both
    discovered by running this suite against the real analyzer rather than a
    mock: unparseable bytes report {"analysis_error": ...} (making the run
    'degraded'), and a flat solid fill has ~zero Laplacian variance and trips
    the real blur heuristic (making the gate reject it) -- accurate behaviour
    in both cases, but not what a happy-path test should be asserting
    against. Striping the image gives it enough edge content to read as
    in-focus.
    """
    img = Image.new("RGB", (800, 600), (60, 120, 200))
    draw = ImageDraw.Draw(img)
    for x in range(0, 800, 40):
        draw.rectangle([x, 0, x + 20, 600], fill=(220, 200, 40))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    return buf.getvalue()


def _fake_assets() -> UploadedAssets:
    return UploadedAssets(
        original=ImageAsset(
            role="original", object_key="users/1/meals/1/original.jpg",
            content_type="image/jpeg", byte_size=1000, sha256="a" * 64,
            image_format="JPEG", width=800, height=600,
        ),
        thumbnail=ImageAsset(
            role="thumbnail", object_key="users/1/meals/1/thumbnail.jpg",
            content_type="image/jpeg", byte_size=100, sha256="b" * 64,
            image_format="JPEG", width=256, height=192,
        ),
    )


@pytest.fixture(autouse=True)
def _stub_r2(monkeypatch):
    monkeypatch.setattr(meals, "is_r2_configured", lambda: True)


def _upload(monkeypatch, committed_user_id: int, vision_payload: dict) -> "meals.MealUploadResponse":
    monkeypatch.setattr(meals, "upload_meal_images", lambda *a, **k: _fake_assets())
    monkeypatch.setattr(meals, "run_image_quality_graph", lambda _content: vision_payload)
    return meals.create_meal_with_metadata(
        committed_user_id, "web_upload", metadata={"filename": "test.jpg"},
        content=_real_jpeg_bytes(),
        content_type="image/jpeg", filename="test.jpg",
    )


ACCEPTED_VISION = {
    "food_detection": {"is_food_image": True, "food_confidence": 90},
    "recommended_action": "continue_with_high_confidence",
}
REJECTED_VISION = {
    "food_detection": {"is_food_image": False, "food_confidence": 5},
    "recommended_action": "reject",
}
DEGRADED_VISION = {"analysis_error": "connection reset"}


class TestHappyPath:
    def test_accepted_meal_is_committed_with_full_analysis(self, monkeypatch, cur, committed_user_id):
        resp = _upload(monkeypatch, committed_user_id, ACCEPTED_VISION)

        assert resp.status == "completed"
        assert resp.nutrition_ready is True
        assert resp.image_url is not None
        assert resp.thumbnail_url is not None

        cur.execute("SELECT lifecycle FROM meals WHERE meal_id = %s", (resp.meal_id,))
        assert cur.fetchone()["lifecycle"] == "stored"

        cur.execute(
            "SELECT count(*) AS n FROM meal_images WHERE meal_id = %s", (resp.meal_id,)
        )
        assert cur.fetchone()["n"] == 2

        cur.execute(
            "SELECT count(*) AS n FROM analysis_artifacts WHERE meal_id = %s",
            (resp.meal_id,),
        )
        assert cur.fetchone()["n"] == 2

        cur.execute(
            "SELECT status FROM analysis_runs WHERE meal_id = %s", (resp.meal_id,)
        )
        assert cur.fetchone()["status"] == "succeeded"

    def test_rejected_meal_has_a_message_and_no_nutrition(self, monkeypatch, committed_user_id):
        resp = _upload(monkeypatch, committed_user_id, REJECTED_VISION)
        assert resp.status == "rejected"
        assert resp.nutrition_ready is False
        assert resp.message


class TestDegradedAnalysis:
    def test_vision_failure_still_produces_a_stored_meal(self, monkeypatch, cur, committed_user_id):
        """Fails open at the storage gate; fails closed at the nutrition gate.

        Both must be true simultaneously: the meal is still usable (an
        Anthropic outage must not reject every upload), but it must not claim
        to be nutrition_ready off the strength of an analyzer that never ran.
        """
        resp = _upload(monkeypatch, committed_user_id, DEGRADED_VISION)

        assert resp.status == "completed"
        assert resp.nutrition_ready is False

        cur.execute(
            "SELECT status FROM analysis_runs WHERE meal_id = %s", (resp.meal_id,)
        )
        assert cur.fetchone()["status"] == "degraded"

        cur.execute(
            "SELECT status, error_code FROM analysis_artifacts "
            "WHERE meal_id = %s AND stage = 'vision_quality'",
            (resp.meal_id,),
        )
        row = cur.fetchone()
        assert row["status"] == "error"
        assert "connection reset" in row["error_code"]


class TestStorageFailure:
    def test_r2_failure_leaves_a_recorded_failed_meal(self, monkeypatch, cur, committed_user_id):
        """The regression this redesign exists to prevent.

        Before the transaction split, an R2 failure rolled back the entire
        INSERT and the meal vanished without a trace. Now the meal row
        (committed in its own transaction before R2 is touched) survives,
        carrying the reason, instead of disappearing.
        """

        def _boom(*a, **k):
            raise RuntimeError("R2 upload failed (SimulatedOutage): test")

        monkeypatch.setattr(meals, "upload_meal_images", _boom)

        with pytest.raises(RuntimeError, match="SimulatedOutage"):
            meals.create_meal_with_metadata(
                committed_user_id, "web_upload", metadata={},
                content=b"x", content_type="image/jpeg", filename="x.jpg",
            )

        cur.execute(
            "SELECT lifecycle, failure_reason FROM meals WHERE user_id = %s "
            "ORDER BY meal_id DESC LIMIT 1",
            (committed_user_id,),
        )
        row = cur.fetchone()
        assert row["lifecycle"] == "failed"
        assert "SimulatedOutage" in row["failure_reason"]

    def test_missing_r2_config_creates_no_meal(self, monkeypatch, cur, committed_user_id):
        """Checked before any row is written, so a bad deploy leaves nothing
        half-created."""
        monkeypatch.setattr(meals, "is_r2_configured", lambda: False)

        cur.execute("SELECT count(*) AS n FROM meals WHERE user_id = %s", (committed_user_id,))
        before = cur.fetchone()["n"]

        with pytest.raises(RuntimeError, match="R2 is not configured"):
            meals.create_meal_with_metadata(
                committed_user_id, "web_upload", metadata={},
                content=b"x", content_type="image/jpeg", filename="x.jpg",
            )

        cur.execute("SELECT count(*) AS n FROM meals WHERE user_id = %s", (committed_user_id,))
        assert cur.fetchone()["n"] == before
