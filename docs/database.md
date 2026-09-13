# Database Schema

The Platter database is organized around a core concept: **one table owns one kind of fact**. This separation enables clean schema evolution and precise state tracking.

## Core Principles

1. **Single Responsibility**: Each table owns exactly one kind of data (meal identity, analysis output, storage state, etc.)
2. **Closed vs. Open Enums**: Values expected to grow use lookup tables (INSERT to extend); genuinely closed sets use CHECK constraints
3. **Derived Values as Views**: Computed values are views, not stored columns—this keeps them in sync with their rules
4. **Explicit NULL Semantics**: NULL means "legitimately unknown", never "not filled in yet"

---

## Lookup Tables

**Purpose**: Enable adding new values as data, not DDL. Without these, adding a new pipeline stage or upload source would require a schema migration.

### `meal_sources`
Where meals originated. Currently only 'web_upload'; mobile, share-sheet, and tracker-import will be added as INSERTs.

| Column | Type | Notes |
|--------|------|-------|
| `source` | TEXT PRIMARY KEY | 'web_upload', etc. |
| `description` | TEXT | Human-readable label |

### `image_roles`
Different stored variants of meal images. Both 'original' and 'thumbnail' are written on successful upload.

| Column | Type | Notes |
|--------|------|-------|
| `role` | TEXT PRIMARY KEY | 'original', 'thumbnail' |
| `description` | TEXT | What this variant is used for |

### `analysis_stages`
Pipeline stages that can produce analysis output. Seeded ahead of implementation—code ships without a schema migration.

| Column | Type | Notes |
|--------|------|-------|
| `stage` | TEXT PRIMARY KEY | e.g., 'vision_quality', 'visible_foods' |
| `description` | TEXT | What this stage computes |
| `is_model_stage` | BOOLEAN | Whether this stage calls an LLM/model |
| `sort_order` | INTEGER | Pipeline order for display |
| `retired_at` | TIMESTAMPTZ | Soft retirement flag; NULL = active |

---

## Users

### `users`
Individual user accounts. One row per person.

| Column | Type | Notes |
|--------|------|-------|
| `user_id` | BIGSERIAL PRIMARY KEY | Used in JWT 'sub' claim |
| `user_name` | TEXT | Display name |
| `user_email` | TEXT UNIQUE | Lowercased; CHECK constraint pins the invariant |
| `user_password_hash` | TEXT | Bcrypt hash |
| `daily_caloric_target` | INTEGER | 500–10000 bounds (mirrored from API constraints) |
| `timezone` | TEXT | IANA zone name (e.g., 'America/Toronto'); enables meal-type inference |
| `created_at` | TIMESTAMPTZ | Account creation |
| `updated_at` | TIMESTAMPTZ | Auto-maintained by trigger |

---

## Meals & Images

### `meals`
The meal record itself: who ate, when, where it came from. Separates concerns: identity, storage state, and analysis are different tables.

| Column | Type | Notes |
|--------|------|-------|
| `meal_id` | BIGSERIAL PRIMARY KEY | |
| `user_id` | BIGINT FK | References `users` |
| `source` | TEXT FK | References `meal_sources` |
| `lifecycle` | TEXT | 'pending' \| 'stored' \| 'failed'—STORAGE only, not analysis quality |
| `failure_reason` | TEXT | Operator-facing (never shown to users); required if `lifecycle = 'failed'` |
| `captured_at_local` | TIMESTAMP | EXIF wall-clock time (local, no zone); NULL if absent |
| `captured_at_offset_minutes` | INTEGER | EXIF offset if known; enables recovery of actual UTC instant |
| `created_at` | TIMESTAMPTZ | Server time of upload |
| `stored_at` | TIMESTAMPTZ | When bytes landed in R2; NULL until `lifecycle = 'stored'` |
| `updated_at` | TIMESTAMPTZ | Auto-maintained by trigger |

**Key Insight**: `lifecycle` tracks **storage**, not analysis quality. A meal can be:
- `lifecycle='stored', accepted=false` (stored but rejected by quality gate)
- `lifecycle='stored', nutrition_ready=true` (stored and analyzed, eligible for nutrition)
- `lifecycle='failed'` (never made it to storage)

### `meal_images`
One row per stored image variant. A failed thumbnail is an absent row, not a failed column.

| Column | Type | Notes |
|--------|------|-------|
| `image_id` | BIGSERIAL PRIMARY KEY | |
| `meal_id` | BIGINT FK | References `meals` |
| `role` | TEXT FK | References `image_roles` ('original', 'thumbnail') |
| `object_key` | TEXT NOT NULL | R2 object key; load-bearing (not nullable) |
| `content_type` | TEXT | MIME type (e.g., 'image/jpeg') |
| `image_format` | TEXT | Pillow format string (e.g., 'JPEG'); drives Log card title |
| `byte_size` | BIGINT | > 0 |
| `width`, `height` | INTEGER | Image dimensions |
| `sha256` | CHAR(64) | Hex SHA-256 hash; enables re-upload idempotency detection |
| `created_at` | TIMESTAMPTZ | |
| UNIQUE | `(meal_id, role)` | One variant per role per meal |

### `meal_image_exif`
The complete EXIF payload, stored losslessly as JSONB. 1:1 with meals (no surrogate ID needed).

| Column | Type | Notes |
|--------|------|-------|
| `meal_id` | BIGINT PRIMARY KEY FK | References `meals` |
| `has_exif` | BOOLEAN | Was EXIF data present? |
| `exif` | JSONB | Full EXIF dict; empty object if absent |

---

## Analysis Pipeline

The pipeline runs per meal, creating **runs** containing **artifacts** (one per stage). Re-analysis is a new run, never an overwrite.

### `analysis_runs`
One row per pipeline invocation over a meal. Tracks why it happened and its overall outcome.

| Column | Type | Notes |
|--------|------|-------|
| `run_id` | BIGSERIAL PRIMARY KEY | |
| `meal_id` | BIGINT FK | References `meals` |
| `trigger` | TEXT | 'upload' \| 'reanalysis' |
| `pipeline_version` | TEXT | Assembly of stages; bumped when graph shape changes |
| `status` | TEXT | 'running' \| 'succeeded' \| 'degraded' \| 'failed' |
| `started_at` | TIMESTAMPTZ | |
| `finished_at` | TIMESTAMPTZ | NULL = run didn't reach its end (crash, timeout) |
| UNIQUE | `(run_id, meal_id)` | Enables denormalization in child tables |

### `analysis_artifacts`
One row per (run, stage). Partial failures are persisted, not swallowed.

| Column | Type | Notes |
|--------|------|-------|
| `artifact_id` | BIGSERIAL PRIMARY KEY | |
| `run_id` | BIGINT FK | References `analysis_runs` |
| `meal_id` | BIGINT | Denormalized (composite FK to `analysis_runs`) |
| `stage` | TEXT FK | References `analysis_stages` |
| `status` | TEXT | 'ok' \| 'error' \| 'skipped' |
| `payload` | JSONB | Model output or computation result |
| `error_code` | TEXT | Set if `status = 'error'` |
| `model_id` | TEXT | Which model generated this artifact |
| `prompt_version` | TEXT | Prompt revision that produced this |
| `config_hash` | TEXT | Hash of deterministic config (e.g., OpenCV thresholds) |
| `latency_ms` | INTEGER | Wall-clock runtime of this stage |
| `created_at` | TIMESTAMPTZ | |
| UNIQUE | `(run_id, stage)` | One artifact per stage per run |
| FK | `(run_id, meal_id)` | Composite FK to `analysis_runs` |

### `meal_gate_verdicts`
The quality gate decision, promoted from JSONB to a typed table. One row per run.

| Column | Type | Notes |
|--------|------|-------|
| `run_id` | BIGINT PRIMARY KEY FK | References `analysis_runs` |
| `meal_id` | BIGINT | Redundant but required for FK |
| `accepted` | BOOLEAN | Storage gate result (fails open) |
| `usability_status` | TEXT | 'usable' \| 'rejected' |
| `recommended_action` | TEXT | Model's recommendation; unconstrained (may change) |
| `is_food_image` | BOOLEAN | Is this actually food? |
| `food_confidence` | REAL | 0–1 (model reports 0–100; normalized here) |
| `message` | TEXT | User-facing copy (shown only if rejected) |
| `nutrition_ready` | BOOLEAN | Nutrition gate result (fails closed) |
| `nutrition_blocked_reason` | TEXT | 'not_food' \| 'vision_unavailable' \| 'photo_rejected' if not ready |
| `analysis_complete` | BOOLEAN | Did both analysers actually run? |
| `rules_version` | TEXT | Gate rule revision; enables comparing old verdicts |
| `created_at` | TIMESTAMPTZ | |
| FK | `(run_id, meal_id)` | Composite FK to `analysis_runs` |

**Key Constraints** (structural invariants):
- `accepted = (usability_status = 'usable')`
- `accepted OR message IS NOT NULL` (rejected meals must have a reason)
- `nutrition_ready = (nutrition_blocked_reason IS NULL)` (gate open ↔ no blocker)

### `meal_foods`
Identified foods from the meal's latest run. A derived projection (rebuilding from `visible_foods` is possible).

| Column | Type | Notes |
|--------|------|-------|
| `meal_food_id` | BIGSERIAL PRIMARY KEY | |
| `run_id` | BIGINT FK | References `analysis_runs` |
| `meal_id` | BIGINT | Denormalized; composite FK to `analysis_runs` |
| `ordinal` | INTEGER | Position in model output; stable sort order |
| `label` | TEXT | Food category (e.g., 'chicken breast') |
| `label_norm` | TEXT GENERATED | Lowercase, trimmed; used for USDA matching |
| `confidence` | REAL | Per-item confidence, 0–1 |
| `possible_types` | TEXT[] | Ambiguous types (e.g., ["raw", "cooked"]) |
| `possible_preparations` | TEXT[] | Ambiguous preparations |
| UNIQUE | `(run_id, ordinal)` | One food per position per run |
| FK | `(run_id, meal_id)` | Composite FK to `analysis_runs` |

---

## Views

Views provide the **stable read contract** to the API. If an artifact's internal shape changes, the view absorbs it and no consumer changes.

### `v_meal_latest_run`
The newest run per meal. User-facing display always shows the latest analysis.

**Key Point**: "Latest coherent set" is exact, not inferred. This prevents a re-run of one stage from silently pairing with an earlier gate verdict.

### `v_meal_local_time`
Best available local wall-clock reading for a meal, ranked by trustworthiness:
1. **exif_local** — Camera's own clock (most trustworthy)
2. **user_timezone** — Server time converted to user's zone
3. **server_utc** — No zone known (often wrong by hours)

Disclosing the source allows consumers to weight confidence accordingly.

### `v_meal_derived_context`
Inferred meal type from local time:
- 05:00–10:59 → 'breakfast'
- 11:00–15:59 → 'lunch'
- 16:00–21:59 → 'dinner'
- 22:00–04:59 → 'late_night'

Computed on read (not stored) so rule changes take effect immediately.

### `v_meal_foods`
Identified foods from the meal's **latest run only**. Stale foods from superseded runs are structurally unreachable.

### `v_meal_list`
Serves `GET /api/meals`. A row per meal with its latest analysis state.

**Status Derivation** (backward compatibility):
| Storage | Verdict | Status |
|---------|---------|--------|
| failed | — | rejected |
| pending | — | processing |
| stored | NULL | processing (analysis in flight) |
| stored | accepted=true | completed |
| stored | accepted=false | rejected |

### `v_meal_detail`
Serves `GET /api/meals/{meal_id}`. Everything in the list row, plus full verdict, run provenance, and aggregated foods as JSON.

### `v_analysis_stage_status`
Per-stage outcome for a meal's latest run. Used for debugging and the "which stage failed?" question.

---

## Relationships at a Glance

```
users
  ↓
meals
  ├→ meal_images (one per role)
  ├→ meal_image_exif
  └→ analysis_runs
      └→ analysis_artifacts
      └→ meal_gate_verdicts
      └→ meal_foods

meal_sources ←─ meals
image_roles  ←─ meal_images
analysis_stages ← analysis_artifacts
```

---

## Key Design Decisions

1. **Lifecycle ≠ Quality**: `meals.lifecycle` tracks storage only ('pending', 'stored', 'failed'). Quality (accepted/rejected) is separate in `meal_gate_verdicts`.

2. **One Run, Many Artifacts**: A pipeline run groups a coherent set of stage outputs. Partial failures are preserved, enabling graceful degradation.

3. **Artifacts Are Immutable**: Re-running a stage creates a new run; old artifacts stay for debugging and offline re-analysis.

4. **Derived Projections**: `meal_foods` rebuilds from `visible_foods` if needed, keeping the source of truth explicit.

5. **Timezone Inference**: `users.timezone` (IANA name) + `meals.captured_at_local` enable accurate meal-type classification without assuming UTC.

6. **Normalization is Explicit**: `meal_foods.label_norm` is GENERATED ALWAYS STORED, pinning the invariant that labels never desync from their normalized form.
