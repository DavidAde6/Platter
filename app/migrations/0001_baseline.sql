-- 0001 — Baseline schema.
--
-- This replaces an earlier baseline that was itself reconstructed from code.
-- It provisions a fresh database from nothing; there is no backfill path,
-- because the only data it ever ran against was disposable dev data.
--
-- Organising rules, applied throughout:
--
--   1. One table owns one kind of fact. A meal's identity, its stored bytes,
--      a pipeline stage's raw output, and a derived verdict are four different
--      kinds of fact and live in four different tables.
--   2. Enums expected to GROW are lookup tables with foreign keys, so
--      extending them is an INSERT. Enums that are genuinely closed stay as
--      CHECK constraints. Each choice is noted where it is made.
--   3. Derived values are VIEWS, not columns. A stored derivation is a value
--      frozen against the rule that produced it; when the rule changes, every
--      old row is quietly wrong and there is nothing to recompute from.
--   4. Nullable means "legitimately unknown", never "not filled in yet". If a
--      write path needs a placeholder, the row belongs in another table.
--
-- Applied by app/migrate.py, in one transaction, tracked in schema_migrations.


-- ---------------------------------------------------------------------------
-- Shared trigger function: keeps updated_at honest without app cooperation.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;


-- ===========================================================================
-- LOOKUP TABLES
--
-- These exist so that adding a value is data, not DDL. The old schema spelled
-- all three as CHECK (x IN (...)), which meant a new upload source or a new
-- pipeline stage required DROP CONSTRAINT + ADD CONSTRAINT — a schema
-- migration to add a string.
-- ===========================================================================

-- 'web_upload' today. Mobile, share-sheet, and tracker-import will follow.
CREATE TABLE meal_sources (
    source      TEXT PRIMARY KEY,
    description TEXT NOT NULL
);

-- 'original' and 'thumbnail' today. A preprocessed 1568px variant is the
-- obvious next one: every vision stage currently re-decodes and re-encodes the
-- original independently (graph/builder.py _to_jpeg_b64, image_quality.py).
CREATE TABLE image_roles (
    role        TEXT PRIMARY KEY,
    description TEXT NOT NULL
);

-- One row per stage the pipeline can produce output for. Seeded in 0002 with
-- every stage named in docs/AnalysisPipeline.md, including ones not built yet
-- — seeding a row is not the same as shipping the stage, and it means
-- shipping the stage needs no migration.
CREATE TABLE analysis_stages (
    stage          TEXT PRIMARY KEY,
    description    TEXT NOT NULL,
    -- False for pure-Python stages (quality_context, fused_analysis), which
    -- leaves model_id / prompt_version legitimately NULL on their artifacts.
    is_model_stage BOOLEAN NOT NULL,
    -- Pipeline order, for display and for "which stage is furthest along".
    sort_order     INTEGER NOT NULL,
    -- Soft retirement. A stage that stops being run must not be deleted:
    -- its historical artifacts still reference it. Set this instead, and the
    -- old payloads stay readable.
    retired_at     TIMESTAMPTZ
);


-- ===========================================================================
-- USERS
-- ===========================================================================

-- user_id stays BIGSERIAL. auth.py puts it in the JWT 'sub' as str(user_id)
-- and parses it back with int(), so moving to UUID would invalidate every
-- issued token and buy nothing.
CREATE TABLE users (
    user_id              BIGSERIAL PRIMARY KEY,
    user_name            TEXT NOT NULL,
    -- users.py already lowercases on both read and write. The CHECK pins the
    -- invariant that UNIQUE silently depends on: without it, one write path
    -- that forgets to normalise makes two rows that are "the same" account.
    user_email           TEXT NOT NULL UNIQUE CHECK (user_email = lower(user_email)),
    user_password_hash   TEXT NOT NULL,
    -- Mirrors the ge=500 / le=10000 bounds the API already enforces. The
    -- database should not accept what the API rejects.
    daily_caloric_target INTEGER CHECK (daily_caloric_target BETWEEN 500 AND 10000),
    -- IANA zone name, e.g. 'America/Toronto'. NULL = not known yet.
    --
    -- This is what makes created_at usable. EXIF capture time is absent on a
    -- large share of web uploads (desktop files, screenshots, anything whose
    -- metadata was stripped on share), and created_at is the only timestamp
    -- always present — but it is UTC server time, so without a zone there is
    -- no local hour, and without a local hour there is no meal type.
    timezone             TEXT,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TRIGGER users_updated_at
    BEFORE UPDATE ON users
    FOR EACH ROW
    EXECUTE FUNCTION set_updated_at();


-- ===========================================================================
-- MEALS
-- ===========================================================================

-- The meal itself: who ate it, when, where the record came from. Nothing
-- about bytes, nothing about analysis.
--
-- Replaces meal_uploads, which additionally held storage state (status,
-- processed_at), a user-facing analysis verdict (rejection_reason), and two
-- R2 object keys. Four concerns in one row — and the status enum could not
-- express the state Phase 2 actually produces: "stored and accepted, but not
-- eligible for a nutrition estimate".
CREATE TABLE meals (
    meal_id           BIGSERIAL PRIMARY KEY,
    user_id           BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    source            TEXT NOT NULL REFERENCES meal_sources(source),

    -- STORAGE lifecycle only: "did we manage to store this upload?" It says
    -- nothing about whether the photo was any good — that is the verdict's
    -- job, and conflating the two is what made the old status column unable
    -- to express "stored and accepted but not nutrition_ready".
    --
    -- This column exists because the upload no longer runs in one
    -- transaction. The meal row is committed before the bytes reach R2, so
    -- an R2 failure leaves a meal with no images — and without a lifecycle
    -- there is no way to tell that apart from an analysis still in flight.
    -- It would read as 'processing' forever.
    --
    -- 'pending' is now a real, durable state rather than one that never
    -- survives a request. That is also precisely the state an async pipeline
    -- needs, so this is the one piece of the redesign that pre-pays for it.
    lifecycle         TEXT NOT NULL DEFAULT 'pending'
                          CHECK (lifecycle IN ('pending', 'stored', 'failed')),
    -- Operator-facing. Never shown to a user: user copy is the verdict's
    -- message, which quality_decision.py owns.
    failure_reason    TEXT,

    -- NAIVE ON PURPOSE. EXIF DateTimeOriginal carries no zone; its wall-clock
    -- reading is already local to wherever the photo was taken, which is what
    -- meal-type inference wants. The previous schema stamped that string as
    -- UTC, producing a column that was right as an hour and wrong as an
    -- instant — unusable for ordering or arithmetic, and silently so. A naive
    -- timestamp states what is actually known.
    captured_at_local TIMESTAMP,
    -- The offset, when it is genuinely known (EXIF OffsetTimeOriginal, or a
    -- client-supplied zone). Storing the offset rather than a derived UTC
    -- instant keeps strictly more information: the instant is computable from
    -- these two, but the offset is not recoverable from the instant alone.
    -- NULL is the common case and that is fine.
    captured_at_offset_minutes INTEGER
                          CHECK (captured_at_offset_minutes BETWEEN -840 AND 840),

    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    -- When the bytes actually landed. NULL until lifecycle = 'stored'.
    stored_at         TIMESTAMPTZ,
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Coherence. These pin invariants that otherwise live only in whichever
    -- Python function happens to write the row.
    CONSTRAINT meals_failed_needs_reason
        CHECK (lifecycle <> 'failed' OR failure_reason IS NOT NULL),
    CONSTRAINT meals_stored_needs_timestamp
        CHECK (lifecycle <> 'stored' OR stored_at IS NOT NULL),
    CONSTRAINT meals_offset_needs_local_time
        CHECK (captured_at_offset_minutes IS NULL OR captured_at_local IS NOT NULL)
);

CREATE TRIGGER meals_updated_at
    BEFORE UPDATE ON meals
    FOR EACH ROW
    EXECUTE FUNCTION set_updated_at();

-- The Log query: WHERE user_id = %s ORDER BY created_at DESC.
CREATE INDEX meals_user_created_idx ON meals (user_id, created_at DESC);


-- ---------------------------------------------------------------------------
-- meal_images — one row per stored variant.
--
-- Replaces meal_uploads.image_url / thumbnail_url, which were misnamed (they
-- held R2 object keys, not URLs), nullable (they had to be — the write path
-- INSERTed the row before uploading), and positional (a third variant would
-- have meant a third column pair).
--
-- Three defects this closes:
--
--   * object_key NOT NULL. The key cannot be recomputed from (user_id,
--     meal_id): storage._extension() derives the extension from the content
--     type or, failing that, from an arbitrary client-supplied filename. A
--     lost key means unaddressable bytes, so the column must never be empty.
--   * A failed thumbnail is an ABSENT ROW. The old write path set
--     thumbnail_key = original_key on failure, so the schema claimed a
--     thumbnail existed and served a full-size image in its place.
--   * width / height live here. They were being stored inside
--     image_qualities.detected_issues.technical.resolution — the same fact, in
--     another table, inside a model-shaped JSONB payload.
-- ---------------------------------------------------------------------------
CREATE TABLE meal_images (
    image_id     BIGSERIAL PRIMARY KEY,
    meal_id      BIGINT NOT NULL REFERENCES meals(meal_id) ON DELETE CASCADE,
    role         TEXT NOT NULL REFERENCES image_roles(role),

    object_key   TEXT NOT NULL,
    content_type TEXT NOT NULL,
    -- Pillow's format string, e.g. 'JPEG'. Distinct from the MIME content
    -- type, and load-bearing: the Log card title is built from it.
    image_format TEXT,
    byte_size    BIGINT NOT NULL CHECK (byte_size > 0),
    width        INTEGER CHECK (width > 0),
    height       INTEGER CHECK (height > 0),
    -- Hex SHA-256 of the stored bytes. Nothing reads it yet; it is here
    -- because it is free at write time and impossible to recover later
    -- without re-downloading every object. Enables re-upload idempotency and
    -- duplicate detection.
    --
    -- Deliberately NOT UNIQUE. Whether a re-upload of identical bytes is the
    -- same meal or a new one is a product question; a UNIQUE constraint would
    -- answer it with a 500 and would block a deliberate re-scan. Persist the
    -- hash now, decide the behaviour later.
    sha256       CHAR(64) NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'),

    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- One variant per role per meal. Also the index serving the image proxy's
    -- (meal_id, role) lookup, which replaces the f-string column whitelist
    -- the old code needed.
    UNIQUE (meal_id, role)
);

CREATE INDEX meal_images_sha256_idx ON meal_images (sha256);


-- ---------------------------------------------------------------------------
-- meal_image_exif — the whole EXIF payload, losslessly.
--
-- The old image_metadata cherry-picked 13 columns and dropped everything else
-- extract_image_metadata() produced: width, height, mode, file_size_bytes,
-- filename, software, exposure_time, f_number, focal_length_35mm, the full
-- flat exif dict, and GPS. Every additional field was a migration, and the
-- discarded ones were gone for good.
--
-- JSONB instead. No generated columns yet: nothing queries camera make/model,
-- and as a recommendation input they are a device/wealth proxy that should not
-- be conditioning anything. Add an expression index when a query needs one.
--
-- PRIMARY KEY is the FOREIGN KEY: this is 1:1 with a meal and needs no
-- surrogate id of its own.
-- ---------------------------------------------------------------------------
CREATE TABLE meal_image_exif (
    meal_id  BIGINT PRIMARY KEY REFERENCES meals(meal_id) ON DELETE CASCADE,
    has_exif BOOLEAN NOT NULL,
    exif     JSONB NOT NULL DEFAULT '{}'::jsonb
);


-- ===========================================================================
-- ANALYSIS
--
-- The old schema had two competing patterns here. image_qualities was UNIQUE
-- on meal_id, so re-running the gate destroyed the previous payload;
-- meal_food_analysis was created specifically to escape that, which left the
-- quality gate as a special case outside the model every other stage would
-- use. Both are replaced by one pattern: a run, and artifacts within it.
-- ===========================================================================

-- One row per invocation of the pipeline over a meal. Re-analysis is a new
-- run, never an overwrite — which is what makes prompt iteration and offline
-- re-runs against stored artifacts possible.
CREATE TABLE analysis_runs (
    run_id           BIGSERIAL PRIMARY KEY,
    meal_id          BIGINT NOT NULL REFERENCES meals(meal_id) ON DELETE CASCADE,
    -- Why this run happened. Distinguishes the upload-time run from a later
    -- re-run after a prompt change, which is the whole point of keeping runs.
    trigger          TEXT NOT NULL CHECK (trigger IN ('upload', 'reanalysis')),
    -- Which assembly of stages this run represents. Bump when the graph shape
    -- changes, so runs stay comparable.
    pipeline_version TEXT NOT NULL,
    -- 'degraded' is the state this schema exists to be able to express: some
    -- stage returned an analysis_error, so the run neither succeeded cleanly
    -- nor failed. Graceful degradation is a product rule, not an edge case,
    -- and a schema that can only say succeeded/failed cannot record it.
    status           TEXT NOT NULL DEFAULT 'running'
                         CHECK (status IN ('running', 'succeeded', 'degraded', 'failed')),
    started_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    -- NULL means the run did not reach its end: a crash, a timeout, or a
    -- process that died mid-pipeline. This is a real, durable state now.
    finished_at      TIMESTAMPTZ,

    -- Redundant given the primary key, but it is what lets child tables carry
    -- a denormalised meal_id under a COMPOSITE foreign key -- see
    -- analysis_artifacts below.
    UNIQUE (run_id, meal_id)
);

CREATE INDEX analysis_runs_meal_idx ON analysis_runs (meal_id, started_at DESC);


-- One row per (run, stage). Partial failures are persisted, not swallowed.
CREATE TABLE analysis_artifacts (
    artifact_id    BIGSERIAL PRIMARY KEY,
    run_id         BIGINT NOT NULL,
    -- Denormalised from the run, because the hot read is "this meal's stage
    -- X" and that index needs meal_id on the artifact itself. The composite
    -- foreign key at the bottom of the table is what stops the denormalised
    -- copy from ever disagreeing with the run's own meal_id -- it makes the
    -- inconsistency unrepresentable rather than merely unlikely.
    meal_id        BIGINT NOT NULL,
    stage          TEXT NOT NULL REFERENCES analysis_stages(stage),

    -- CHECK rather than a lookup table, deliberately, and in contrast to
    -- `stage` above: a stage's outcome is either produced, failed, or was
    -- never attempted. That set is closed. `stage` is not.
    status         TEXT NOT NULL CHECK (status IN ('ok', 'error', 'skipped')),

    payload        JSONB NOT NULL DEFAULT '{}'::jsonb,
    -- Set when status = 'error'. The payload may ALSO carry the pipeline's own
    -- {"analysis_error": "..."} sentinel — graph/ still emits it and
    -- quality_decision._ran() still depends on it. This column is the
    -- queryable form, not a replacement.
    error_code     TEXT,

    -- Provenance. None of this was recorded before, which made a stored
    -- payload untraceable to whatever produced it.
    model_id       TEXT,
    prompt_version TEXT,
    -- Hash of the deterministic configuration behind this artifact — for the
    -- technical stage, the OpenCV thresholds in image_quality.py. Those are
    -- module constants that were never persisted, so a stored payload could
    -- not be re-interpreted after a threshold change: you could see
    -- "issue: true" but not what bar it failed to clear.
    config_hash    TEXT,

    -- Wall-clock cost of this stage. Free to capture, and it is the number
    -- that decides the sync-to-async switch: PLANS.txt lists a p95 over ~30s
    -- and a gateway timeout as triggers, and flags both as unverified. There
    -- is no way to verify them retroactively, so start measuring on the day
    -- the second model call ships.
    latency_ms     INTEGER CHECK (latency_ms >= 0),

    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE (run_id, stage),
    FOREIGN KEY (run_id, meal_id)
        REFERENCES analysis_runs (run_id, meal_id) ON DELETE CASCADE
);

-- The hot read: "latest payload for this meal's stage X".
CREATE INDEX analysis_artifacts_meal_stage_idx
    ON analysis_artifacts (meal_id, stage, created_at DESC);
-- "Every artifact of stage X produced under an outdated prompt", for
-- targeted re-analysis after a prompt revision.
CREATE INDEX analysis_artifacts_prompt_idx ON analysis_artifacts (stage, prompt_version);
-- "What is failing, and since when" — a partial index, so it stays small.
CREATE INDEX analysis_artifacts_errors_idx
    ON analysis_artifacts (stage, created_at DESC) WHERE status = 'error';


-- ---------------------------------------------------------------------------
-- meal_gate_verdicts — the gate decision, promoted out of JSONB.
--
-- A column-per-field projection of quality_decision.QualityDecision. A real
-- table rather than a view over the artifact payload because it is an
-- app-owned shape rather than a model output, it is read on every list and
-- every detail request, and nutrition_ready has to be indexable.
--
-- The old schema promoted exactly one of these nine fields (is_food_image) to
-- a column and left the rest inside detected_issues — while also writing the
-- entire decision into detected_issues["decision"], so the promoted column
-- duplicated a nested value. Two representations, no stated winner.
-- ---------------------------------------------------------------------------
CREATE TABLE meal_gate_verdicts (
    run_id                   BIGINT PRIMARY KEY,
    meal_id                  BIGINT NOT NULL,

    -- Storage gate. Fails OPEN: absent analysis must not reject a photo.
    accepted                 BOOLEAN NOT NULL,
    usability_status         TEXT NOT NULL CHECK (usability_status IN ('usable', 'rejected')),
    -- Deliberately UNCONSTRAINED. This value is echoed straight from the
    -- vision model. Pinning it to today's enum would turn a prompt or schema
    -- revision into a 500 on upload. Constrain what we compute, never what a
    -- model emits.
    recommended_action       TEXT,
    is_food_image            BOOLEAN,
    -- Normalised 0-1. The model reports 0-100; quality_decision converts.
    food_confidence          REAL CHECK (food_confidence BETWEEN 0 AND 1),
    -- User-facing copy, set only when rejected.
    message                  TEXT,

    -- Nutrition gate. Fails CLOSED: requires positive evidence of food.
    -- Everything that emits a calorie or macro number branches on this, never
    -- on `accepted`.
    nutrition_ready          BOOLEAN NOT NULL,
    nutrition_blocked_reason TEXT CHECK (nutrition_blocked_reason IN
                                 ('not_food', 'vision_unavailable', 'photo_rejected')),
    -- Did both analysers actually run? A meal can be nutrition_ready with
    -- this false; downstream should discount confidence, not refuse.
    analysis_complete        BOOLEAN NOT NULL,

    -- Which revision of the gating rules produced this verdict. Without it, a
    -- rules change is invisible in the data and old verdicts are silently
    -- incomparable with new ones.
    rules_version            TEXT NOT NULL,

    created_at               TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    FOREIGN KEY (run_id, meal_id)
        REFERENCES analysis_runs (run_id, meal_id) ON DELETE CASCADE,

    -- The three invariants evaluate_quality() guarantees structurally, and
    -- which until now existed only in Python and its tests. A refactor that
    -- desyncs them should fail at the write, not ship an incoherent verdict.
    CONSTRAINT verdict_status_coherent
        CHECK (accepted = (usability_status = 'usable')),
    CONSTRAINT verdict_message_coherent
        CHECK (accepted OR message IS NOT NULL),
    CONSTRAINT verdict_gate_coherent
        CHECK (nutrition_ready = (nutrition_blocked_reason IS NULL))
);

CREATE INDEX meal_gate_verdicts_meal_idx ON meal_gate_verdicts (meal_id, created_at DESC);
-- "Which meals may receive a nutrition estimate" — the Phase 2 work queue.
CREATE INDEX meal_gate_verdicts_nutrition_idx
    ON meal_gate_verdicts (nutrition_ready) WHERE nutrition_ready;


-- ---------------------------------------------------------------------------
-- meal_foods — the identified foods, one row each.
--
-- A DERIVED PROJECTION, not a source of truth. The visible_foods artifact is
-- authoritative and lossless; this table is rebuildable from it at any time.
-- Keeping that distinction explicit is what stops it becoming a second,
-- diverging copy.
--
-- It exists because the two queries that matter downstream are relational:
-- Phase 2 joins labels to USDA matches, and Discover asks for a user's recent
-- food labels. Neither should be a JSON path scan over every artifact row.
-- ---------------------------------------------------------------------------
CREATE TABLE meal_foods (
    meal_food_id          BIGSERIAL PRIMARY KEY,
    run_id                BIGINT NOT NULL,
    meal_id               BIGINT NOT NULL,
    -- Position within the model's output, so display order is stable.
    ordinal               INTEGER NOT NULL,

    -- Coarse category — the thing a nutrition lookup matches on.
    label                 TEXT NOT NULL,
    -- The join key for everything downstream: Phase 2 matches this against a
    -- USDA lookup cache, and a later avoid-list checks membership against it.
    -- Generated rather than written, so it can never drift from `label`, and
    -- indexed so those are index lookups rather than scans.
    label_norm            TEXT GENERATED ALWAYS AS (lower(btrim(label))) STORED,
    -- Unresolved ambiguity, kept explicit. Multiple plausible entries mean a
    -- macro RANGE widened across all of them, never a single pick.
    possible_types        TEXT[] NOT NULL DEFAULT '{}',
    possible_preparations TEXT[] NOT NULL DEFAULT '{}',
    -- Per-item, 0-1. Global confidence belongs on the verdict, not here.
    confidence            REAL CHECK (confidence BETWEEN 0 AND 1),

    UNIQUE (run_id, ordinal),
    FOREIGN KEY (run_id, meal_id)
        REFERENCES analysis_runs (run_id, meal_id) ON DELETE CASCADE
);

CREATE INDEX meal_foods_meal_idx  ON meal_foods (meal_id);
CREATE INDEX meal_foods_label_idx ON meal_foods (label_norm);


-- ===========================================================================
-- VIEWS — the stable read contract
--
-- The API reads views. It never reads a model-shaped JSONB payload, and it
-- never reconstructs a derived value in Python. When an artifact's internal
-- shape changes, the view absorbs it and no consumer changes.
-- ===========================================================================

-- All views are CREATE OR REPLACE so a later migration can re-run this whole
-- section. CAVEAT: CREATE OR REPLACE VIEW cannot change a column's name, type
-- or position. To reshape one, the migration must DROP VIEW ... CASCADE first,
-- in dependency order:
--     v_meal_detail -> v_meal_foods -> v_meal_list
--                   -> v_meal_derived_context -> v_meal_local_time
--                   -> v_meal_latest_run


-- The newest run per meal. Everything user-facing shows the latest analysis;
-- older runs are kept for debugging and offline re-runs, not for display.
--
-- This is what makes "latest coherent set" exact rather than inferred. Re-run
-- one stage without a run to group by, and a later foods payload silently
-- pairs with an earlier gate verdict.
CREATE OR REPLACE VIEW v_meal_latest_run AS
SELECT DISTINCT ON (meal_id)
       meal_id,
       run_id,
       trigger,
       pipeline_version,
       status,
       started_at,
       finished_at
FROM analysis_runs
ORDER BY meal_id, started_at DESC, run_id DESC;


-- The best local wall-clock reading available for a meal, plus WHICH source
-- it came from.
--
-- Three tiers, most to least trustworthy:
--   exif_local    — the camera's own wall clock, local to where the photo was
--                   taken. Absent on a large share of web uploads.
--   user_timezone — server time converted into the user's stated zone.
--   server_utc    — no zone known, so UTC. Frequently wrong by hours.
--
-- Disclosing the source rather than collapsing all three is what lets a
-- consumer decide how much to trust the derived meal type, instead of the
-- old column's flat 'unknown' which conflated "no data" with "late night".
CREATE OR REPLACE VIEW v_meal_local_time AS
SELECT m.meal_id,
       CASE WHEN m.captured_at_local IS NOT NULL THEN 'exif_local'
            WHEN u.timezone IS NOT NULL          THEN 'user_timezone'
            ELSE 'server_utc'
       END AS meal_time_source,
       COALESCE(
           m.captured_at_local,
           m.created_at AT TIME ZONE COALESCE(u.timezone, 'UTC')
       ) AS local_captured_at
FROM meals m
JOIN users u ON u.user_id = m.user_id;


-- likely_meal_type, computed on read.
--
-- This was a stored column, written once at upload time and read by nobody.
-- Two problems with that: a change to the bucketing rule silently stranded
-- every existing row, and the old rule dropped 22:00–05:00 into 'unknown',
-- which is a real eating window rather than missing data. As a view it is
-- always current, and 'late_night' is a real answer.
--
-- This goes back to being a column the moment users can CORRECT it — at that
-- point it is input rather than derivation, and the view becomes
-- COALESCE(meals.meal_type_override, derived).
CREATE OR REPLACE VIEW v_meal_derived_context AS
SELECT meal_id,
       meal_time_source,
       local_captured_at,
       CASE
           WHEN local_hour >= 5  AND local_hour < 11 THEN 'breakfast'
           WHEN local_hour >= 11 AND local_hour < 16 THEN 'lunch'
           WHEN local_hour >= 16 AND local_hour < 22 THEN 'dinner'
           ELSE 'late_night'
       END AS likely_meal_type
FROM (
    SELECT meal_id,
           meal_time_source,
           local_captured_at,
           EXTRACT(HOUR FROM local_captured_at)::int AS local_hour
    FROM v_meal_local_time
) t;


-- The identified foods of each meal's LATEST run.
--
-- Scoping to the latest run here, once, is what makes stale foods from a
-- superseded run structurally unreachable rather than avoided by convention
-- at each call site.
CREATE OR REPLACE VIEW v_meal_foods AS
SELECT f.meal_id,
       f.ordinal,
       f.label,
       f.label_norm,
       f.confidence,
       f.possible_types,
       f.possible_preparations
FROM meal_foods f
JOIN v_meal_latest_run r ON r.run_id = f.run_id;


-- Serves GET /api/meals.
--
-- `status` is derived here for backward compatibility: the frontend switches
-- on it, and the old three-valued column is gone. This CASE is the single
-- auditable place where two genuinely separate facts — did we store it, and
-- was it any good — get collapsed back into the client's three values.
--
--   lifecycle 'failed'  -> 'rejected'    the one deliberate lie. A storage
--                                        failure is not a bad photo, but the
--                                        client contract has no word for it.
--   lifecycle 'pending' -> 'processing'
--   no verdict yet      -> 'processing'  keyed off the VERDICT, not the run:
--                                        a run that started and never wrote a
--                                        verdict is still in progress.
--
-- Note that 'processing' can now outlive a request, which it never could
-- before. Log.tsx renders this string raw with no per-value branching, so
-- adding a fourth value later is a copy decision, not a breaking change.
--
-- has_original / has_thumbnail are booleans rather than keys on purpose. The
-- client is never given an object key or a presigned URL; storage.py turns
-- these into authenticated proxy paths derived from (meal_id, role). Booleans
-- also close a silent-failure hole: the old code probed meal.get("image_url")
-- and yielded None -- a vanished image, no error -- if the projection changed.
CREATE OR REPLACE VIEW v_meal_list AS
SELECT m.meal_id,
       m.user_id,
       m.source,
       m.created_at,
       m.lifecycle,
       orig.image_format,
       orig.width,
       orig.height,
       (orig.image_id IS NOT NULL) AS has_original,
       (thumb.image_id IS NOT NULL) AS has_thumbnail,
       CASE
           WHEN m.lifecycle = 'failed'  THEN 'rejected'
           WHEN m.lifecycle = 'pending' THEN 'processing'
           WHEN v.accepted IS NULL      THEN 'processing'
           WHEN v.accepted              THEN 'completed'
           ELSE 'rejected'
       END AS status,
       COALESCE(v.nutrition_ready, FALSE) AS nutrition_ready,
       v.nutrition_blocked_reason,
       -- User-facing copy comes only from the verdict. failure_reason is
       -- operator-facing and must never leak to a client.
       v.message AS rejection_reason,
       dc.likely_meal_type,
       dc.meal_time_source,
       r.finished_at AS processed_at
FROM meals m
LEFT JOIN meal_images orig  ON orig.meal_id  = m.meal_id AND orig.role  = 'original'
LEFT JOIN meal_images thumb ON thumb.meal_id = m.meal_id AND thumb.role = 'thumbnail'
LEFT JOIN v_meal_latest_run r ON r.meal_id = m.meal_id
LEFT JOIN meal_gate_verdicts v ON v.run_id = r.run_id
LEFT JOIN v_meal_derived_context dc ON dc.meal_id = m.meal_id;


-- Serves GET /api/meals/{meal_id}: everything in the list row, plus the full
-- gate verdict, run provenance, and the identified foods. Foods are
-- aggregated to JSON so the endpoint is a single row and the caller does no
-- stitching. Built ON v_meal_list rather than duplicating its status CASE —
-- one definition, two consumers.
CREATE OR REPLACE VIEW v_meal_detail AS
SELECT l.*,
       r.run_id,
       r.pipeline_version,
       r.status AS run_status,
       v.usability_status,
       v.recommended_action,
       v.is_food_image,
       v.food_confidence,
       v.analysis_complete,
       v.rules_version,
       COALESCE(f.foods, '[]'::json) AS foods
FROM v_meal_list l
LEFT JOIN v_meal_latest_run r ON r.meal_id = l.meal_id
LEFT JOIN meal_gate_verdicts v ON v.run_id = r.run_id
LEFT JOIN LATERAL (
    SELECT json_agg(
               json_build_object(
                   'label', mf.label,
                   'possible_types', mf.possible_types,
                   'possible_preparations', mf.possible_preparations,
                   'confidence', mf.confidence
               ) ORDER BY mf.ordinal
           ) AS foods
    FROM meal_foods mf
    WHERE mf.run_id = r.run_id
) f ON TRUE;


-- Per-stage outcome for a meal's latest run. Serves debugging and the
-- "which stage failed" question, without any consumer touching a payload.
CREATE OR REPLACE VIEW v_analysis_stage_status AS
SELECT a.meal_id,
       a.stage,
       a.status,
       a.error_code,
       a.model_id,
       a.prompt_version,
       a.config_hash,
       a.latency_ms,
       a.created_at
FROM analysis_artifacts a
JOIN v_meal_latest_run r ON r.run_id = a.run_id;
