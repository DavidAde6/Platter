"""The derivation logic that lives in views instead of application code.

Each test here pins a specific behaviour that used to be either wrong (the
UTC-stamped captured_at), silent (thumbnail aliasing), or absent (a fourth
meal-type bucket) in the schema this one replaces.
"""

from __future__ import annotations

import pytest


def _insert_meal(cur, user_id, **kwargs):
    columns = ["user_id", "source", *kwargs.keys()]
    placeholders = ", ".join(["%s"] * len(columns))
    cur.execute(
        f"INSERT INTO meals ({', '.join(columns)}) VALUES ({placeholders}) "
        "RETURNING meal_id",
        (user_id, "web_upload", *kwargs.values()),
    )
    return cur.fetchone()["meal_id"]


class TestMealType:
    """v_meal_derived_context: the view that replaced a stored, unread column."""

    @pytest.mark.parametrize(
        "hour, expected",
        [
            (6, "breakfast"),
            (12, "lunch"),
            (18, "dinner"),
            (23, "late_night"),  # the old rule's 'unknown' hole
            (2, "late_night"),
        ],
    )
    def test_hour_buckets(self, cur, user_id, hour, expected):
        meal_id = _insert_meal(
            cur, user_id, captured_at_local=f"2026-09-12 {hour:02d}:00:00"
        )
        cur.execute(
            "SELECT likely_meal_type FROM v_meal_derived_context WHERE meal_id = %s",
            (meal_id,),
        )
        assert cur.fetchone()["likely_meal_type"] == expected

    def test_source_is_exif_when_captured_at_local_present(self, cur, user_id):
        meal_id = _insert_meal(cur, user_id, captured_at_local="2026-09-12 19:00:00")
        cur.execute(
            "SELECT meal_time_source FROM v_meal_derived_context WHERE meal_id = %s",
            (meal_id,),
        )
        assert cur.fetchone()["meal_time_source"] == "exif_local"

    def test_source_is_user_timezone_without_exif(self, cur, user_id):
        # The user_id fixture sets timezone='America/Toronto'.
        meal_id = _insert_meal(cur, user_id)
        cur.execute(
            "SELECT meal_time_source FROM v_meal_derived_context WHERE meal_id = %s",
            (meal_id,),
        )
        assert cur.fetchone()["meal_time_source"] == "user_timezone"

    def test_source_is_server_utc_without_timezone_or_exif(self, cur):
        cur.execute(
            "INSERT INTO users (user_name, user_email, user_password_hash, timezone) "
            "VALUES ('NoTz', 'notz@example.com', 'x', NULL) RETURNING user_id"
        )
        uid = cur.fetchone()["user_id"]
        meal_id = _insert_meal(cur, uid)
        cur.execute(
            "SELECT meal_time_source FROM v_meal_derived_context WHERE meal_id = %s",
            (meal_id,),
        )
        assert cur.fetchone()["meal_time_source"] == "server_utc"


class TestMealListStatus:
    """v_meal_list.status: the CASE that collapses lifecycle + verdict into
    the three-valued string the frontend still switches on."""

    def test_pending_reads_as_processing(self, cur, meal_id):
        cur.execute("SELECT status FROM v_meal_list WHERE meal_id = %s", (meal_id,))
        assert cur.fetchone()["status"] == "processing"

    def test_failed_reads_as_rejected(self, cur, user_id):
        cur.execute(
            "INSERT INTO meals (user_id, source, lifecycle, failure_reason) "
            "VALUES (%s, 'web_upload', 'failed', 'R2 down') RETURNING meal_id",
            (user_id,),
        )
        meal_id = cur.fetchone()["meal_id"]
        cur.execute(
            "SELECT status, rejection_reason FROM v_meal_list WHERE meal_id = %s",
            (meal_id,),
        )
        row = cur.fetchone()
        assert row["status"] == "rejected"
        # The operator-facing failure_reason must never leak as user copy.
        assert row["rejection_reason"] is None

    def test_stored_with_no_run_is_still_processing(self, cur, user_id):
        cur.execute(
            "INSERT INTO meals (user_id, source, lifecycle, stored_at) "
            "VALUES (%s, 'web_upload', 'stored', NOW()) RETURNING meal_id",
            (user_id,),
        )
        meal_id = cur.fetchone()["meal_id"]
        cur.execute("SELECT status FROM v_meal_list WHERE meal_id = %s", (meal_id,))
        assert cur.fetchone()["status"] == "processing"

    def _stored_meal_with_verdict(self, cur, user_id, accepted, nutrition_ready):
        cur.execute(
            "INSERT INTO meals (user_id, source, lifecycle, stored_at) "
            "VALUES (%s, 'web_upload', 'stored', NOW()) RETURNING meal_id",
            (user_id,),
        )
        meal_id = cur.fetchone()["meal_id"]
        cur.execute(
            "INSERT INTO analysis_runs (meal_id, trigger, pipeline_version, "
            "status, finished_at) VALUES (%s, 'upload', 'test', 'succeeded', NOW()) "
            "RETURNING run_id",
            (meal_id,),
        )
        run_id = cur.fetchone()["run_id"]
        cur.execute(
            "INSERT INTO meal_gate_verdicts (run_id, meal_id, accepted, "
            "usability_status, nutrition_ready, nutrition_blocked_reason, "
            "analysis_complete, rules_version, message) VALUES "
            "(%s, %s, %s, %s, %s, %s, TRUE, 'r/1', %s)",
            (
                run_id,
                meal_id,
                accepted,
                "usable" if accepted else "rejected",
                nutrition_ready,
                None if nutrition_ready else "photo_rejected",
                None if accepted else "not usable",
            ),
        )
        return meal_id

    def test_accepted_reads_as_completed(self, cur, user_id):
        meal_id = self._stored_meal_with_verdict(cur, user_id, True, True)
        cur.execute(
            "SELECT status, nutrition_ready FROM v_meal_list WHERE meal_id = %s",
            (meal_id,),
        )
        row = cur.fetchone()
        assert row["status"] == "completed"
        assert row["nutrition_ready"] is True

    def test_rejected_reads_as_rejected(self, cur, user_id):
        meal_id = self._stored_meal_with_verdict(cur, user_id, False, False)
        cur.execute("SELECT status FROM v_meal_list WHERE meal_id = %s", (meal_id,))
        assert cur.fetchone()["status"] == "rejected"


class TestImageFlags:
    """has_original / has_thumbnail: absence must read as absence."""

    def test_no_images_means_both_false(self, cur, meal_id):
        cur.execute(
            "SELECT has_original, has_thumbnail FROM v_meal_list WHERE meal_id = %s",
            (meal_id,),
        )
        row = cur.fetchone()
        assert row["has_original"] is False
        assert row["has_thumbnail"] is False

    def test_missing_thumbnail_is_not_aliased_to_original(self, cur, meal_id):
        """The defect this schema was built to remove: a failed thumbnail used
        to be recorded as a second copy of the original's key. Here, storing
        only an 'original' row must leave has_thumbnail false -- never true."""
        cur.execute(
            "INSERT INTO meal_images (meal_id, role, object_key, content_type, "
            "byte_size, sha256) VALUES (%s, 'original', 'k', 'image/jpeg', 100, %s)",
            (meal_id, "a" * 64),
        )
        cur.execute(
            "SELECT has_original, has_thumbnail, image_format "
            "FROM v_meal_list WHERE meal_id = %s",
            (meal_id,),
        )
        row = cur.fetchone()
        assert row["has_original"] is True
        assert row["has_thumbnail"] is False


class TestLatestRunWins:
    """A superseded run's foods and verdict must not surface anywhere."""

    def test_v_meal_foods_reflects_only_the_newest_run(self, cur, meal_id):
        cur.execute(
            "INSERT INTO analysis_runs (meal_id, trigger, pipeline_version, "
            "started_at) VALUES (%s, 'upload', 'v1', NOW() - interval '1 hour') "
            "RETURNING run_id",
            (meal_id,),
        )
        old_run = cur.fetchone()["run_id"]
        cur.execute(
            "INSERT INTO meal_foods (run_id, meal_id, ordinal, label) "
            "VALUES (%s, %s, 0, 'old label')",
            (old_run, meal_id),
        )

        cur.execute(
            "INSERT INTO analysis_runs (meal_id, trigger, pipeline_version) "
            "VALUES (%s, 'reanalysis', 'v2') RETURNING run_id",
            (meal_id,),
        )
        new_run = cur.fetchone()["run_id"]
        cur.execute(
            "INSERT INTO meal_foods (run_id, meal_id, ordinal, label) "
            "VALUES (%s, %s, 0, 'new label')",
            (new_run, meal_id),
        )

        cur.execute("SELECT label FROM v_meal_foods WHERE meal_id = %s", (meal_id,))
        labels = [row["label"] for row in cur.fetchall()]
        assert labels == ["new label"]


def test_label_norm_is_generated_and_indexable(cur, meal_id):
    cur.execute(
        "INSERT INTO analysis_runs (meal_id, trigger, pipeline_version) "
        "VALUES (%s, 'upload', 'test') RETURNING run_id",
        (meal_id,),
    )
    run_id = cur.fetchone()["run_id"]
    cur.execute(
        "INSERT INTO meal_foods (run_id, meal_id, ordinal, label) "
        "VALUES (%s, %s, 0, '  Jollof Rice  ')",
        (run_id, meal_id),
    )
    cur.execute("SELECT label_norm FROM meal_foods WHERE run_id = %s", (run_id,))
    assert cur.fetchone()["label_norm"] == "jollof rice"
