"""Repository round-trips, and the one security-relevant invariant: ownership.

meals.py documents the ownership check as the actual safety win over a
presigned URL (a caller can never learn whether a meal_id belongs to someone
else, an image variant was never stored, or the meal does not exist -- all
three read as None/404). It was previously untested.
"""

from __future__ import annotations

from quality_decision import QualityDecision
from repositories import analysis as analysis_repo
from repositories import images as images_repo
from repositories import meals as meals_repo
from repositories import users as users_repo


def _other_user(cur) -> int:
    cur.execute(
        "INSERT INTO users (user_name, user_email, user_password_hash) "
        "VALUES ('Other', 'other@example.com', 'x') RETURNING user_id"
    )
    return cur.fetchone()["user_id"]


class TestFullRoundTrip:
    def test_insert_through_get_detail(self, cur, user_id):
        mid = meals_repo.insert_meal(cur, user_id=user_id, source="web_upload")

        images_repo.insert_image(
            cur, meal_id=mid, role="original", object_key="k/orig",
            content_type="image/jpeg", image_format="JPEG",
            byte_size=1000, width=800, height=600, sha256="a" * 64,
        )
        images_repo.insert_image(
            cur, meal_id=mid, role="thumbnail", object_key="k/thumb",
            content_type="image/jpeg", image_format="JPEG",
            byte_size=100, width=256, height=192, sha256="b" * 64,
        )
        images_repo.insert_exif(cur, meal_id=mid, has_exif=True, exif={"Make": "Apple"})
        meals_repo.mark_stored(cur, mid)

        run_id = analysis_repo.start_run(cur, meal_id=mid, pipeline_version="test")
        analysis_repo.insert_artifact(
            cur, run_id=run_id, meal_id=mid, stage="technical_quality",
            status="ok", payload={"has_issues": False},
        )
        analysis_repo.insert_verdict(
            cur, run_id=run_id, meal_id=mid, rules_version="r/1",
            decision=QualityDecision(
                accepted=True, usability_status="usable", recommended_action="accept",
                is_food_image=True, food_confidence=0.9, message=None,
                nutrition_ready=True, nutrition_blocked_reason=None,
                analysis_complete=True,
            ),
        )
        n = analysis_repo.replace_foods(
            cur, run_id=run_id, meal_id=mid,
            foods=[{"label": "rice", "confidence": 0.8}],
        )
        analysis_repo.finish_run(cur, run_id=run_id, status="succeeded")

        assert n == 1

        detail = meals_repo.get_detail(cur, user_id=user_id, meal_id=mid)
        assert detail is not None
        assert detail.status == "completed"
        assert detail.nutrition_ready is True
        assert detail.has_original and detail.has_thumbnail
        assert [f["label"] for f in detail.foods] == ["rice"]

        rows = meals_repo.list_for_user(cur, user_id)
        assert [r.meal_id for r in rows] == [mid]


class TestOwnership:
    def test_get_detail_hides_other_users_meals(self, cur, user_id, meal_id):
        other = _other_user(cur)
        assert meals_repo.get_detail(cur, user_id=other, meal_id=meal_id) is None
        assert meals_repo.get_detail(cur, user_id=user_id, meal_id=meal_id) is not None

    def test_list_for_user_never_crosses_users(self, cur, user_id, meal_id):
        other = _other_user(cur)
        other_meal = meals_repo.insert_meal(cur, user_id=other, source="web_upload")

        mine = {r.meal_id for r in meals_repo.list_for_user(cur, user_id)}
        theirs = {r.meal_id for r in meals_repo.list_for_user(cur, other)}

        assert meal_id in mine and other_meal not in mine
        assert other_meal in theirs and meal_id not in theirs

    def test_get_object_ref_enforces_ownership(self, cur, user_id, meal_id):
        images_repo.insert_image(
            cur, meal_id=meal_id, role="original", object_key="k",
            content_type="image/jpeg", byte_size=1, sha256="c" * 64,
        )
        other = _other_user(cur)

        assert images_repo.get_object_ref(
            cur, user_id=user_id, meal_id=meal_id, role="original"
        ) is not None
        assert images_repo.get_object_ref(
            cur, user_id=other, meal_id=meal_id, role="original"
        ) is None

    def test_get_object_ref_absent_variant_is_none_not_original(self, cur, user_id, meal_id):
        """The variant that used to be silently aliased to the original."""
        images_repo.insert_image(
            cur, meal_id=meal_id, role="original", object_key="k",
            content_type="image/jpeg", byte_size=1, sha256="d" * 64,
        )
        ref = images_repo.get_object_ref(
            cur, user_id=user_id, meal_id=meal_id, role="thumbnail"
        )
        assert ref is None


class TestUpsertIsIdempotent:
    def test_re_inserting_same_role_updates_rather_than_conflicts(self, cur, meal_id):
        first = images_repo.insert_image(
            cur, meal_id=meal_id, role="original", object_key="k1",
            content_type="image/jpeg", byte_size=100, sha256="e" * 64,
        )
        second = images_repo.insert_image(
            cur, meal_id=meal_id, role="original", object_key="k2",
            content_type="image/jpeg", byte_size=200, sha256="f" * 64,
        )
        assert first == second  # same row, updated in place

        cur.execute(
            "SELECT object_key, byte_size FROM meal_images WHERE image_id = %s",
            (first,),
        )
        row = cur.fetchone()
        assert row["object_key"] == "k2"
        assert row["byte_size"] == 200


def test_email_lowercased_on_insert(cur):
    row = users_repo.insert_user(
        cur, user_name="Case", user_email="Mixed@Example.COM", password_hash="x"
    )
    assert row["user_email"] == "mixed@example.com"


def test_duplicate_email_raises_domain_error(cur):
    users_repo.insert_user(
        cur, user_name="First", user_email="dup@example.com", password_hash="x"
    )
    try:
        with cur.connection.transaction():
            users_repo.insert_user(
                cur, user_name="Second", user_email="dup@example.com", password_hash="x"
            )
        raise AssertionError("expected EmailAlreadyExists")
    except users_repo.EmailAlreadyExists:
        pass


def test_update_rejects_unknown_column(cur, user_id):
    try:
        users_repo.update_user(cur, user_id, {"user_password_hash_typo": "x"})
        raise AssertionError("expected ValueError for an unwhitelisted column")
    except ValueError:
        pass
