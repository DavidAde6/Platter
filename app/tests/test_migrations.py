"""The migrations apply cleanly, and the objects they claim to create exist.

This is the check that would have caught the original problem: PLANS.txt
records that meal_uploads and image_metadata had no DDL in the repo at all,
reconstructed after the fact from application code. Running the migrations
against an empty schema and asserting the result is what makes that class of
drift impossible to miss.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.usefixtures("migrated_db")

EXPECTED_TABLES = {
    "schema_migrations",
    "meal_sources",
    "image_roles",
    "analysis_stages",
    "users",
    "meals",
    "meal_images",
    "meal_image_exif",
    "analysis_runs",
    "analysis_artifacts",
    "meal_gate_verdicts",
    "meal_foods",
}

EXPECTED_VIEWS = {
    "v_meal_latest_run",
    "v_meal_local_time",
    "v_meal_derived_context",
    "v_meal_foods",
    "v_meal_list",
    "v_meal_detail",
    "v_analysis_stage_status",
}


def test_expected_tables_exist(cur):
    cur.execute(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema = 'public' AND table_type = 'BASE TABLE'"
    )
    found = {row["table_name"] for row in cur.fetchall()}
    missing = EXPECTED_TABLES - found
    assert not missing, f"migrations did not create: {sorted(missing)}"


def test_expected_views_exist(cur):
    cur.execute(
        "SELECT table_name FROM information_schema.views WHERE table_schema = 'public'"
    )
    found = {row["table_name"] for row in cur.fetchall()}
    missing = EXPECTED_VIEWS - found
    assert not missing, f"migrations did not create: {sorted(missing)}"


@pytest.mark.parametrize("view", sorted(EXPECTED_VIEWS))
def test_every_view_is_queryable(cur, view):
    """Catches a typo in a view body immediately, rather than at first use."""
    cur.execute(f"SELECT * FROM {view} LIMIT 0")


def test_migrate_again_applies_nothing(migrated_db):
    """Re-running migrate() against an already-migrated schema is a no-op."""
    import os

    import migrate

    old_url = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = migrated_db
    try:
        assert migrate.migrate() == 0
    finally:
        if old_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = old_url


def test_analysis_stages_seeded(cur):
    cur.execute("SELECT stage, is_model_stage FROM analysis_stages ORDER BY sort_order")
    stages = cur.fetchall()
    names = [row["stage"] for row in stages]
    assert names == [
        "technical_quality",
        "vision_quality",
        "quality_context",
        "visible_foods",
        "segmentation",
        "fused_analysis",
        "nutrition",
    ]
    # is_model_stage is what lets NULL model_id/prompt_version on an artifact
    # be expected rather than suspicious -- check it isn't seeded backwards.
    model_stages = {row["stage"] for row in stages if row["is_model_stage"]}
    assert model_stages == {"vision_quality", "visible_foods", "segmentation", "nutrition"}


def test_lookup_rows_seeded(cur):
    cur.execute("SELECT source FROM meal_sources")
    assert {row["source"] for row in cur.fetchall()} == {"web_upload"}

    cur.execute("SELECT role FROM image_roles")
    assert {row["role"] for row in cur.fetchall()} == {"original", "thumbnail"}
