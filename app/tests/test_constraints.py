"""The invariants the schema is supposed to make unrepresentable.

Each of these mirrors a defect in the schema this one replaced. The point of
the test is not "constraints exist" -- it is "the specific bad state that used
to be possible now raises", so a future migration that loosens a constraint by
accident fails here instead of shipping a silent regression.
"""

from __future__ import annotations

import psycopg
import pytest


def _violates(cur, sql, params=()):
    """True if executing sql raises an integrity or check error.

    Each caller gets its own SAVEPOINT via cur.connection.transaction(), so
    one failed statement does not abort the whole test's outer transaction --
    the rollback fixture in conftest needs that transaction to still be alive
    at teardown.
    """
    try:
        with cur.connection.transaction():
            cur.execute(sql, params)
    except (psycopg.errors.IntegrityError, psycopg.errors.CheckViolation):
        return True
    return False


class TestMealImages:
    """meal_images: object_key NOT NULL, one role per meal, a real hash."""

    def test_object_key_cannot_be_null(self, cur, meal_id):
        assert _violates(
            cur,
            "INSERT INTO meal_images (meal_id, role, object_key, content_type, "
            "byte_size, sha256) VALUES (%s, 'original', NULL, 'image/jpeg', 1, %s)",
            (meal_id, "a" * 64),
        )

    def test_duplicate_role_rejected(self, cur, meal_id):
        cur.execute(
            "INSERT INTO meal_images (meal_id, role, object_key, content_type, "
            "byte_size, sha256) VALUES (%s, 'original', 'k1', 'image/jpeg', 1, %s)",
            (meal_id, "a" * 64),
        )
        assert _violates(
            cur,
            "INSERT INTO meal_images (meal_id, role, object_key, content_type, "
            "byte_size, sha256) VALUES (%s, 'original', 'k2', 'image/jpeg', 1, %s)",
            (meal_id, "b" * 64),
        )

    def test_sha256_must_look_like_a_hash(self, cur, meal_id):
        assert _violates(
            cur,
            "INSERT INTO meal_images (meal_id, role, object_key, content_type, "
            "byte_size, sha256) VALUES (%s, 'thumbnail', 'k', 'image/jpeg', 1, 'nope')",
            (meal_id,),
        )

    def test_unknown_role_rejected(self, cur, meal_id):
        assert _violates(
            cur,
            "INSERT INTO meal_images (meal_id, role, object_key, content_type, "
            "byte_size, sha256) VALUES (%s, 'medium', 'k', 'image/jpeg', 1, %s)",
            (meal_id, "a" * 64),
        )


class TestAnalysisArtifacts:
    """The composite FK to analysis_runs, and the stage lookup."""

    def _run(self, cur, meal_id):
        cur.execute(
            "INSERT INTO analysis_runs (meal_id, trigger, pipeline_version) "
            "VALUES (%s, 'upload', 'test') RETURNING run_id",
            (meal_id,),
        )
        return cur.fetchone()["run_id"]

    def test_unknown_stage_rejected(self, cur, meal_id):
        run_id = self._run(cur, meal_id)
        assert _violates(
            cur,
            "INSERT INTO analysis_artifacts (run_id, meal_id, stage, status, payload) "
            "VALUES (%s, %s, 'not_a_real_stage', 'ok', '{}'::jsonb)",
            (run_id, meal_id),
        )

    def test_meal_id_must_match_its_run(self, cur, meal_id):
        """The denormalised meal_id on an artifact cannot disagree with its run's.

        This is the guard the composite FOREIGN KEY (run_id, meal_id) exists
        for: without it, an artifact could silently attach to a different
        meal than the run it claims to belong to.
        """
        run_id = self._run(cur, meal_id)
        assert _violates(
            cur,
            "INSERT INTO analysis_artifacts (run_id, meal_id, stage, status, payload) "
            "VALUES (%s, %s, 'segmentation', 'ok', '{}'::jsonb)",
            (run_id, meal_id + 999_999),
        )

    def test_unknown_status_rejected(self, cur, meal_id):
        run_id = self._run(cur, meal_id)
        assert _violates(
            cur,
            "INSERT INTO analysis_artifacts (run_id, meal_id, stage, status, payload) "
            "VALUES (%s, %s, 'segmentation', 'maybe', '{}'::jsonb)",
            (run_id, meal_id),
        )


class TestGateVerdicts:
    """The three coherence CHECKs mirror evaluate_quality()'s own invariants."""

    def _run(self, cur, meal_id):
        cur.execute(
            "INSERT INTO analysis_runs (meal_id, trigger, pipeline_version) "
            "VALUES (%s, 'upload', 'test') RETURNING run_id",
            (meal_id,),
        )
        return cur.fetchone()["run_id"]

    def test_nutrition_ready_requires_no_blocked_reason(self, cur, meal_id):
        run_id = self._run(cur, meal_id)
        assert _violates(
            cur,
            "INSERT INTO meal_gate_verdicts (run_id, meal_id, accepted, "
            "usability_status, nutrition_ready, nutrition_blocked_reason, "
            "analysis_complete, rules_version) VALUES "
            "(%s, %s, TRUE, 'usable', TRUE, 'not_food', TRUE, 'r/1')",
            (run_id, meal_id),
        )

    def test_accepted_requires_usable_status(self, cur, meal_id):
        run_id = self._run(cur, meal_id)
        assert _violates(
            cur,
            "INSERT INTO meal_gate_verdicts (run_id, meal_id, accepted, "
            "usability_status, nutrition_ready, analysis_complete, rules_version) "
            "VALUES (%s, %s, TRUE, 'rejected', TRUE, TRUE, 'r/1')",
            (run_id, meal_id),
        )

    def test_rejected_requires_a_message(self, cur, meal_id):
        run_id = self._run(cur, meal_id)
        assert _violates(
            cur,
            "INSERT INTO meal_gate_verdicts (run_id, meal_id, accepted, "
            "usability_status, nutrition_ready, nutrition_blocked_reason, "
            "analysis_complete, rules_version) VALUES "
            "(%s, %s, FALSE, 'rejected', FALSE, 'photo_rejected', TRUE, 'r/1')",
            (run_id, meal_id),
        )

    def test_food_confidence_bounded(self, cur, meal_id):
        run_id = self._run(cur, meal_id)
        assert _violates(
            cur,
            "INSERT INTO meal_gate_verdicts (run_id, meal_id, accepted, "
            "usability_status, food_confidence, nutrition_ready, analysis_complete, "
            "rules_version) VALUES (%s, %s, TRUE, 'usable', 1.5, TRUE, TRUE, 'r/1')",
            (run_id, meal_id),
        )


class TestMeals:
    """Lifecycle coherence: the states the transaction split newly needs."""

    def test_failed_requires_a_reason(self, cur, user_id):
        assert _violates(
            cur,
            "INSERT INTO meals (user_id, source, lifecycle) "
            "VALUES (%s, 'web_upload', 'failed')",
            (user_id,),
        )

    def test_stored_requires_a_timestamp(self, cur, user_id):
        assert _violates(
            cur,
            "INSERT INTO meals (user_id, source, lifecycle) "
            "VALUES (%s, 'web_upload', 'stored')",
            (user_id,),
        )

    def test_offset_requires_a_local_time(self, cur, user_id):
        assert _violates(
            cur,
            "INSERT INTO meals (user_id, source, captured_at_offset_minutes) "
            "VALUES (%s, 'web_upload', -240)",
            (user_id,),
        )


class TestUsers:
    def test_email_must_be_lowercase(self, cur):
        assert _violates(
            cur,
            "INSERT INTO users (user_name, user_email, user_password_hash) "
            "VALUES ('X', 'Mixed@Case.com', 'h')",
        )

    def test_email_uniqueness(self, cur, user_id):
        cur.execute("SELECT user_email FROM users WHERE user_id = %s", (user_id,))
        email = cur.fetchone()["user_email"]
        assert _violates(
            cur,
            "INSERT INTO users (user_name, user_email, user_password_hash) "
            "VALUES ('Dup', %s, 'h')",
            (email,),
        )

    @pytest.mark.parametrize("target", [100, 20000])
    def test_caloric_target_bounded(self, cur, target):
        assert _violates(
            cur,
            "INSERT INTO users (user_name, user_email, user_password_hash, "
            "daily_caloric_target) VALUES ('X', 'bounds@example.com', 'h', %s)",
            (target,),
        )


class TestMealFoods:
    def test_confidence_bounded(self, cur, meal_id):
        cur.execute(
            "INSERT INTO analysis_runs (meal_id, trigger, pipeline_version) "
            "VALUES (%s, 'upload', 'test') RETURNING run_id",
            (meal_id,),
        )
        run_id = cur.fetchone()["run_id"]
        assert _violates(
            cur,
            "INSERT INTO meal_foods (run_id, meal_id, ordinal, label, confidence) "
            "VALUES (%s, %s, 0, 'x', 1.5)",
            (run_id, meal_id),
        )
