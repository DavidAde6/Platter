"""Analysis runs, per-stage artifacts, the gate verdict, and the food projection.

One persistence pattern for every stage. The quality gate is not a special
case here, which is the whole reason this module replaces both
``image_qualities`` and ``meal_food_analysis``.
"""

from __future__ import annotations

from typing import Any, Sequence

from psycopg import Cursor
from psycopg.types.json import Jsonb

from quality_decision import QualityDecision
from repositories.read_models import StageStatusRow


def start_run(
    cur: Cursor,
    *,
    meal_id: int,
    pipeline_version: str,
    trigger: str = "upload",
) -> int:
    """Open a run. Status starts at 'running'; call finish_run to close it."""
    cur.execute(
        """
        INSERT INTO analysis_runs (meal_id, trigger, pipeline_version)
        VALUES (%s, %s, %s)
        RETURNING run_id
        """,
        (meal_id, trigger, pipeline_version),
    )
    return cur.fetchone()["run_id"]


def finish_run(cur: Cursor, *, run_id: int, status: str) -> None:
    """Close a run as 'succeeded', 'degraded' or 'failed'.

    'degraded' is the one that matters: a run where some stage returned an
    analysis_error neither succeeded cleanly nor failed, and a pipeline whose
    contract is "never abort the upload for a degraded stage" needs to be able
    to record that.
    """
    cur.execute(
        "UPDATE analysis_runs SET status = %s, finished_at = NOW() WHERE run_id = %s",
        (status, run_id),
    )


def insert_artifact(
    cur: Cursor,
    *,
    run_id: int,
    meal_id: int,
    stage: str,
    status: str,
    payload: dict[str, Any],
    error_code: str | None = None,
    model_id: str | None = None,
    prompt_version: str | None = None,
    config_hash: str | None = None,
    latency_ms: int | None = None,
) -> int:
    """Persist one stage's raw output, successful or not.

    Partial failures are stored, never swallowed: the payload may legitimately
    be ``{"analysis_error": "..."}``, and that is worth keeping -- it is how a
    degraded stage gets diagnosed after the fact.
    """
    cur.execute(
        """
        INSERT INTO analysis_artifacts (
            run_id, meal_id, stage, status, payload, error_code,
            model_id, prompt_version, config_hash, latency_ms
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING artifact_id
        """,
        (
            run_id,
            meal_id,
            stage,
            status,
            Jsonb(payload),
            error_code,
            model_id,
            prompt_version,
            config_hash,
            latency_ms,
        ),
    )
    return cur.fetchone()["artifact_id"]


def insert_verdict(
    cur: Cursor,
    *,
    run_id: int,
    meal_id: int,
    decision: QualityDecision,
    rules_version: str,
) -> None:
    """Project the QualityDecision into its own row, all nine fields.

    The table's CHECK constraints mirror the invariants evaluate_quality()
    guarantees structurally, so a refactor that desyncs them fails here rather
    than storing an incoherent verdict.
    """
    cur.execute(
        """
        INSERT INTO meal_gate_verdicts (
            run_id, meal_id, accepted, usability_status, recommended_action,
            is_food_image, food_confidence, message, nutrition_ready,
            nutrition_blocked_reason, analysis_complete, rules_version
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            run_id,
            meal_id,
            decision.accepted,
            decision.usability_status,
            decision.recommended_action,
            decision.is_food_image,
            decision.food_confidence,
            decision.message,
            decision.nutrition_ready,
            decision.nutrition_blocked_reason,
            decision.analysis_complete,
            rules_version,
        ),
    )


def replace_foods(
    cur: Cursor,
    *,
    run_id: int,
    meal_id: int,
    foods: Sequence[dict[str, Any]],
) -> int:
    """Rewrite the food projection for one run. Returns the row count.

    A projection, not a source of truth: the visible_foods artifact is
    authoritative, and this is rebuildable from it. Replace-not-append so
    re-projecting an existing run is idempotent.

    Each item takes ``label`` plus optional ``confidence``, ``possible_types``
    and ``possible_preparations``. Ordinal comes from list position, which is
    what keeps display order stable.
    """
    cur.execute("DELETE FROM meal_foods WHERE run_id = %s", (run_id,))
    if not foods:
        return 0

    rows = [
        (
            run_id,
            meal_id,
            ordinal,
            food["label"],
            list(food.get("possible_types") or []),
            list(food.get("possible_preparations") or []),
            food.get("confidence"),
        )
        for ordinal, food in enumerate(foods)
    ]
    cur.executemany(
        """
        INSERT INTO meal_foods (
            run_id, meal_id, ordinal, label,
            possible_types, possible_preparations, confidence
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        """,
        rows,
    )
    return len(rows)


def latest_artifacts(cur: Cursor, meal_id: int) -> dict[str, dict[str, Any]]:
    """Stage name -> payload, for this meal's latest run.

    The one function allowed to hand raw payloads back to Python, because
    reading them is the analysis layer's actual job: reassembling
    ``{"technical": ..., "vision": ...}`` for evaluate_quality(), or feeding
    build_quality_context(). The rule it does not break is that no *API*
    consumer ever sees a payload shape.

    This is also what makes re-analysis possible without re-calling any model:
    the stored artifacts are the inputs.
    """
    cur.execute(
        """
        SELECT a.stage, a.payload
        FROM analysis_artifacts a
        JOIN v_meal_latest_run r ON r.run_id = a.run_id
        WHERE a.meal_id = %s
        """,
        (meal_id,),
    )
    return {row["stage"]: row["payload"] for row in cur.fetchall()}


def stage_status(cur: Cursor, meal_id: int) -> list[StageStatusRow]:
    """Per-stage outcome for the latest run. Debugging, not a product surface."""
    cur.execute(
        """
        SELECT stage, status, error_code, model_id, prompt_version,
               config_hash, latency_ms, created_at
        FROM v_analysis_stage_status
        WHERE meal_id = %s
        ORDER BY stage
        """,
        (meal_id,),
    )
    return [StageStatusRow(**row) for row in cur.fetchall()]
