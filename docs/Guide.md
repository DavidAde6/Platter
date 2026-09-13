# Platter — Developer Guide

Platter is an AI-powered web app that helps users make smarter food choices. The long-term goal: upload a photo of a meal and get ingredient identification plus nutritional estimates using computer vision and ML.

**This guide reflects the codebase as it exists today** — not aspirational docs. Use it as the single source of truth for how upload and analysis work. Scope for v1: [`MVP.md`](MVP.md). Product north star (Discover, fulfillable suggestions, tone): [`Vision.md`](Vision.md).

---

## Table of contents

1. [What works today](#what-works-today)
2. [Architecture](#architecture)
3. [Image upload & analysis lifecycle](#image-upload--analysis-lifecycle)
4. [API reference](#api-reference)
5. [Database schema](#database-schema)
6. [Key source files](#key-source-files)
7. [Environment & local dev](#environment--local-dev)
8. [Planned work](#planned-work)

---

## What works today

| Area | Status |
|------|--------|
| User signup / login (JWT) | ✅ |
| Meal photo upload (web) | ✅ |
| EXIF & image metadata extraction | ✅ |
| Cloudflare R2 storage (original + thumbnail) | ✅ |
| OpenCV technical quality checks | ✅ |
| Claude vision quality analysis (LangGraph) | ✅ |
| Accept / reject gating with user-facing messages | ✅ |
| Meal log (list past uploads) + single-meal detail | ✅ |
| Auth-proxied image serving | ✅ |
| Calorie / macro / ingredient estimation | ❌ not built |
| Segmentation / region masks | ❌ not built |
| Async background analysis | ❌ not built |
| GPS → city/country geocoding | ❌ not wired (coordinates are now persisted in EXIF JSONB, unread) |

Upload analysis today answers one question: **"Is this a usable food photo?"** — not "What's in it and how many calories?"

---

## Architecture

```
Frontend (React + Vite)
  Scan.tsx -> uploadMealImage() -> POST /api/upload
  Log.tsx  -> GET /api/meals, GET /api/meals/{id}
        |
        | Bearer JWT
        v
Backend (FastAPI)
  main.py          - HTTP routes, upload validation
  meals.py         - orchestration only, zero SQL
  users.py         - user service: request/response models, password rules
  repositories/     - every SQL statement in the app
  image_metadata   - Pillow EXIF extraction
  storage.py       - Cloudflare R2 upload/fetch
  image_quality    - OpenCV deterministic checks
  graph/           - LangGraph + Claude vision node
  quality_decision - accept/reject gating
        |                              |
        v                              v
  PostgreSQL (Neon)              Cloudflare R2
  meals, meal_images,             users/{user_id}/meals/{meal_id}/
  meal_image_exif,                  original.* + thumbnail.jpg
  analysis_runs,
  analysis_artifacts,
  meal_gate_verdicts,
  meal_foods
```

**Deployment:** Docker Compose runs backend (`:8000`) and frontend (`:8080`). Production also uses Kubernetes manifests under `k8s/`; removing them is tracked in `PLANS.txt` (Phase 4).

**Design choices:**

- **Three transactions per upload, still one synchronous request.** The client waits for the full result, but no transaction spans R2 or a model call — see [Image upload & analysis lifecycle](#image-upload--analysis-lifecycle).
- **Images always stored** — rejected photos are kept in R2; only the meal's lifecycle and verdict change.
- **No public image URLs** — frontend gets auth-proxied paths (`/api/meals/{id}/image`), not presigned R2 links.
- **Graceful degradation** — a stage's failure is a row (`analysis_artifacts.status = 'error'`), never an aborted transaction.
- **All SQL lives in `repositories/`.** `meals.py` and `users.py` are orchestration; every repository function takes an open cursor and never commits — the caller decides the transaction boundary.
- **The API reads views, never JSONB paths.** `v_meal_list` and `v_meal_detail` are the read contract; no endpoint touches a model's payload shape directly.
- **Pooled connections.** `db.py` holds one `psycopg_pool.ConnectionPool`, opened lazily on first use. Scripts (`migrate.py`, the dev-reset tool) use `connect_direct()` instead — a one-off process gains nothing from a pool.

---

## Image upload & analysis lifecycle

The entire flow runs inside a single `POST /api/upload` request — there is still no queue, webhook, or polling — but it is now **three separate transactions**, not one. The previous version held a single connection open across two R2 round-trips and a Claude call (15–30 seconds of external I/O with a Neon connection pinned the whole time). Nothing slow happens inside a transaction any more.

### Flow diagram

```
User selects photo (Scan.tsx)
        |
        v
POST /api/upload  -- validate (type, size, non-empty)
        |
        v
extract_image_metadata()  -- Pillow: dimensions, format, EXIF
        |
        v
create_meal_with_metadata()  (app/meals.py)
        |
        |  T1: INSERT meals (lifecycle='pending')  -- commit
        |
        |  upload_meal_images() -> R2                -- NO transaction held
        |     (original + 256px JPEG thumbnail; on failure, mark_failed()
        |      records lifecycle='failed' + reason, and re-raises)
        |
        |  T2: INSERT meal_images, meal_image_exif;
        |      UPDATE meals SET lifecycle='stored'   -- commit
        |
        |  run_meal_analysis()                       -- NO transaction held
        |     (OpenCV technical_quality + Claude vision_quality,
        |      each timed; evaluate_quality() combines them)
        |
        |  T3: INSERT analysis_runs, analysis_artifacts (one per stage),
        |      meal_gate_verdicts, meal_foods          -- commit
        |
        v
GET the meal back through v_meal_detail -> MealUploadResponse
```

**What a partial failure looks like now**, which is the entire reason for the split:

| Failure point | Result |
|---|---|
| R2 upload fails | The meal row (already committed in T1) is updated to `lifecycle='failed'` with a reason. The exception still propagates to the client (503), but the attempt is on record instead of vanishing. |
| The vision or technical stage errors | Caught by the same never-raise contract as before; the artifact is stored with `status='error'`, the run is marked `'degraded'`, and the storage gate still resolves (fails open). `nutrition_ready` correctly comes back `false` (fails closed). |
| T3 never lands (crash, timeout) | The meal is `stored` with no run. `v_meal_list` reports `status: "processing"` — which can now genuinely outlive a request. Re-analysis is "start a new run," not "re-upload." |

### Step 1 — HTTP validation

**File:** `app/main.py` → `upload_img()`

| Rule | Value |
|------|-------|
| Allowed content types | `image/jpeg`, `image/png`, `image/webp`, `image/heic`, `image/heif` |
| Max file size | 15 MB |
| Auth | Bearer JWT (`get_current_user_id`) |
| Source tag | `"web_upload"` (only upload source in code today) |

Failures before orchestration return 400 (bad file), 413 (too large), or 503 (R2 misconfigured — checked before any row is written).

### Step 2 — EXIF / metadata extraction

**File:** `app/image_metadata.py` → `extract_image_metadata()`

Extracted via Pillow (returned in the API response and stored **whole** in `meal_image_exif.exif`):

- **Basic:** filename, content type, file size, width, height, mode, format, animated flag, frame count, DPI
- **EXIF:** camera make/model, orientation, capture datetimes, focal length, ISO, flash, lens, GPS coordinates

Metadata extraction failure → 400 before any DB write.

A handful of known-large EXIF blobs (`MakerNote`, `UserComment`, `PrintImageMatching`, `ThumbnailData`) and any single value over 4 KB are pruned before storage — see `meals._exif_for_storage()` — so a big binary tag doesn't push every row into TOAST storage. Pruned keys are recorded in `exif_pruned`.

### Step 3 — Storage (Cloudflare R2)

**File:** `app/storage.py`

| Function | Role |
|----------|------|
| `upload_meal_images()` | Upload original bytes + generate a 256px JPEG thumbnail (quality 85). Returns an `UploadedAssets` dataclass, not a pair of strings — see below. |
| `_object_key()` | `users/{user_id}/meals/{meal_id}/{original\|thumbnail}.{ext}` |
| `meal_image_paths()` | Turn `(has_original, has_thumbnail)` booleans into `/api/meals/{id}/image?variant=...` proxy paths |
| `fetch_meal_image()` | Stream bytes for the image GET endpoint |

`UploadedAssets` carries an `ImageAsset` per variant (`object_key`, `content_type`, `image_format`, `byte_size`, `width`, `height`, `sha256`) computed from the actual bytes, not inferred later. **`thumbnail` is `None` on failure** — it is never aliased to the original's key. A missing thumbnail is an absent row in `meal_images`, not a full-size image quietly standing in for one.

Required env vars: `R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_BUCKET_NAME`. Bucket must stay **private**.

### Step 4 — Technical analysis (OpenCV)

**File:** `app/image_quality.py` → `analyze_image_quality()`

Deterministic checks on a grayscale decode (PIL → numpy → OpenCV). Thresholds are intentionally lenient for normal phone photos.

| Check | Threshold | Stored signal |
|-------|-----------|---------------|
| Blur | Laplacian variance < 60 | `blur.issue` |
| Brightness | Mean intensity < 35 or > 225 | `brightness.issue` |
| Overexposure | >50% pixels ≥ 250 | `overexposure.issue` |
| Underexposure | >50% pixels ≤ 5 | `underexposure.issue` |
| Resolution | Shortest side < 200px | `resolution.issue` |

Decode failures return `{ analysis_error, has_issues: false }` — never raises.

The payload also carries `analyzer_version` and the exact `thresholds` used (`ANALYZER_VERSION`, `analyzer_thresholds()`), hashed into `analysis_artifacts.config_hash`. Without this a stored `technical_quality` artifact couldn't be re-interpreted after a threshold tuning change — `issue: true` would be visible with no record of what bar was failed.

### Step 5 — Vision analysis (Claude via LangGraph)

**Files:** `app/graph/builder.py`, `app/graph/nodes.py`, `app/graph/schema.py`

Pipeline:

1. Decode image (incl. HEIC via `pillow_heif`) → RGB → thumbnail to max 1568px edge → JPEG base64
2. LangGraph `StateGraph` with a **single node** today: `image_quality`
3. Model: **`claude-opus-4-8`** via `ANTHROPIC_API_KEY`, tagged with `PROMPT_VERSION` (`graph/nodes.py`)
4. Structured JSON output constrained by `DETECTED_ISSUES_SCHEMA`

Vision output fields:

| Group | Fields |
|-------|--------|
| `food_detection` | `is_food_image`, `food_confidence` (0–100) |
| `visibility` | `plate_visible`, `cropped_food` (each: value, confidence, severity) |
| `geometry` | `bad_angle`, `depth_unclear` |
| `occlusion` | `food_overlap_level`, `sauce_hiding_food` |
| `portion_estimation` | `portion_difficulty` (value, confidence, reasons) |
| Routing | `recommended_action` |

`recommended_action` values: `accept` · `continue_with_high_confidence` · `continue_with_medium_confidence` · `request_retake` · `reject`

Vision errors return `{ analysis_error: ... }` — never raises. `MODEL` and `PROMPT_VERSION` are recorded on the artifact regardless of outcome.

### Step 6 — Quality gating

**File:** `app/quality_decision.py` → `evaluate_quality()`

Combines `technical` + `vision` signals — still the same function signature and the same 42 tests, unchanged by the schema redesign. There are **two gates with opposite failure preferences**.

**Storage gate (`accepted`) — fails open.**

| Condition | Result |
|-----------|--------|
| `is_food_image == false` | **Reject** — "We couldn't find a meal in this photo…" |
| Any technical check `issue == true` | **Reject** — specific message per check (blur, dark, bright, etc.) |
| `recommended_action` in `{ reject, request_retake }` | **Reject** — "This photo isn't clear enough…" |
| Otherwise | **Accept** → meal reads as `status = "completed"` |

If vision fails entirely (no `is_food_image` / `recommended_action`), the decision falls back to technical checks only. Rejecting every upload during an Anthropic outage would tell users their photo is unclear — false, unactionable, and indistinguishable from a broken product.

**Nutrition gate (`nutrition_ready`) — fails closed.**

`accepted` means "no reason to reject was found", which is *not* the same as "this was checked and is fine". The OpenCV checks measure blur, brightness and resolution; they have no concept of food. So during a vision outage a sharp photo of a dog passes the storage gate.

`nutrition_ready` therefore requires **positive evidence** — `is_food_image is True` — rather than the absence of a rejection:

| `nutrition_blocked_reason` | Meaning |
|---|---|
| `not_food` | Vision confirmed this is not a meal |
| `vision_unavailable` | `is_food_image` was never determined |
| `photo_rejected` | Confirmed food, but the photo failed the storage gate |
| *(None)* | `nutrition_ready == true` |

**Anything downstream that produces a calorie or macro number must branch on `nutrition_ready`, not on `status`.** Both `GET /api/meals` and `GET /api/meals/{id}` now expose `nutrition_ready` directly, so there is no reason to reach for `status` instead.

`analysis_complete` is separate: it reports whether *both* analyzers produced results. A meal can be `nutrition_ready` with `analysis_complete == false` (e.g. OpenCV failed but vision confirmed food) — downstream should discount confidence rather than refuse.

The verdict is tagged with `DECISION_RULES_VERSION` (`quality_decision.py`) and stored as its own row — see [Database schema](#database-schema).

### Step 7 — Lifecycle and status

`meals.lifecycle` (`'pending'` → `'stored'` | `'failed'`) is a storage-only fact: did the upload survive. It says nothing about whether the photo was any good — that is the verdict's job. The two used to be one three-valued `status` column that couldn't express "stored and accepted but not `nutrition_ready`"; they're now separate, and a view collapses them back into the `status` string the frontend still reads:

```
lifecycle = 'failed'           -> status: "rejected"   (the one deliberate lie —
                                                          a storage failure isn't
                                                          a bad photo, but the
                                                          client contract has no
                                                          fourth word for it)
lifecycle = 'pending'          -> status: "processing"
lifecycle = 'stored', no run   -> status: "processing"  (can now outlive a request)
lifecycle = 'stored', accepted -> status: "completed"
lifecycle = 'stored', rejected -> status: "rejected"
```

Rejected (and failed) meals still appear in `GET /api/meals`.

### Step 8 — What gets persisted

Each stage of the pipeline is its own row in `analysis_artifacts`, keyed to an `analysis_runs` row for the upload. Nothing is combined into one JSONB blob any more — see [Database schema](#database-schema) for the full shape.

`v_meal_derived_context.likely_meal_type` is computed on read from the best available local time (EXIF capture time, else the user's stored timezone applied to `created_at`, else UTC):

| Local hour | Type |
|------------|------|
| 05:00–10:59 | breakfast |
| 11:00–15:59 | lunch |
| 16:00–21:59 | dinner |
| 22:00–04:59 | late_night |

There is no `unknown` bucket any more — a real `meal_time_source` field (`exif_local` / `user_timezone` / `server_utc`) reports how confident that bucket is, instead of collapsing "no data" and "genuinely eaten at 11pm" into the same value.

GPS coordinates are extracted and now persisted (inside `meal_image_exif.exif`, alongside everything else the extractor produces) but nothing reads them yet — reverse geocoding is not wired.

---

## API reference

All meal routes require `Authorization: Bearer <token>`.

| Method | Path | Handler | Purpose |
|--------|------|---------|---------|
| `POST` | `/api/upload` | `upload_img` | Upload meal photo (multipart field: `image`) |
| `GET` | `/api/meals` | `get_meals` | List user's meals, newest first (`?limit=`, default 100, max 200) |
| `GET` | `/api/meals/{meal_id}` | `get_meal` | One meal with its gate verdict and identified foods |
| `GET` | `/api/meals/{meal_id}/image?variant=original\|thumbnail` | `get_meal_image` | Auth-proxied image bytes from R2 |
| `POST` | `/api/auth/signup` | `signup` | Create account |
| `POST` | `/api/auth/login` | `login` | Get JWT |
| `GET` | `/api/users/me` | `get_me` | Current user profile |
| `PATCH` | `/api/users/me` | `patch_me` | Update profile |

A meal owned by someone else, or a meal that does not exist, both return **404** from `GET /api/meals/{meal_id}` — a caller cannot distinguish the two. The same rule applies to the image proxy (invalid `object_key` lookups also 404). This is enforced in `repositories/meals.py` and `repositories/images.py` by filtering on `user_id` in the query itself, not by checking ownership after the fact.

### Upload response (`MealUploadResponse`)

```json
{
  "meal_id": 42,
  "status": "completed",
  "image_url": "/api/meals/42/image?variant=original",
  "thumbnail_url": "/api/meals/42/image?variant=thumbnail",
  "metadata": { "...EXIF and dimensions..." },
  "message": null,
  "nutrition_ready": true
}
```

When rejected, `status` is `"rejected"` and `message` contains the user-facing reason.

### Meal detail response (`MealDetail`, `GET /api/meals/{meal_id}`)

Everything in `MealPublic` (the list-row shape), plus:

```json
{
  "width": 4032, "height": 3024,
  "nutrition_blocked_reason": null,
  "usability_status": "usable",
  "recommended_action": "accept",
  "is_food_image": true,
  "food_confidence": 0.91,
  "analysis_complete": true,
  "meal_time_source": "exif_local",
  "foods": [
    { "label": "jollof rice", "possible_types": ["jollof rice", "fried rice"],
      "possible_preparations": [], "confidence": 0.78 }
  ]
}
```

`foods` is `[]` until the M1 visible-foods stage ships; the field always exists.

### Frontend callers

| File | Function | Endpoint |
|------|----------|----------|
| `frontend/src/lib/mealLog.ts` | `uploadMealImage()` | `POST /api/upload` |
| `frontend/src/lib/mealLog.ts` | `fetchMealLog()` | `GET /api/meals` |
| `frontend/src/lib/mealLog.ts` | `fetchMealImageObjectUrl()` | `GET /api/meals/{id}/image` |
| `frontend/src/pages/Scan.tsx` | `uploadFile()` | triggers upload on file select |

`GET /api/meals/{meal_id}` has no frontend caller yet — it exists for the M1 UI work.

---

## Database schema

```
users
  └── meals (1:N)
        ├── meal_images       (1:N, one row per role: original / thumbnail)
        ├── meal_image_exif   (1:1)
        └── analysis_runs     (1:N)
              ├── analysis_artifacts   (1:N, one per stage per run)
              ├── meal_gate_verdicts   (1:1 with a run)
              └── meal_foods           (1:N, one per identified food)

meal_sources, image_roles, analysis_stages   -- lookup tables
```

All child tables `ON DELETE CASCADE`. `analysis_artifacts`, `meal_gate_verdicts` and `meal_foods` additionally carry a **composite foreign key** to `(analysis_runs.run_id, analysis_runs.meal_id)` — this is what makes it structurally impossible for a stored artifact to disagree with its own run about which meal it belongs to.

All DDL lives in `app/migrations/`, applied by `app/migrate.py`. There is a single baseline (`0001_baseline.sql`) plus a seed file (`0002_seed_lookups.sql`) — the dev database this replaced was re-baselined from scratch rather than migrated forward, because its only contents were disposable dev data. See [Environment & local dev](#environment--local-dev) for the reset procedure.

### Why this shape

The schema it replaced had two competing persistence patterns for analysis output (`image_qualities`, `UNIQUE` on `meal_id` — re-running the gate destroyed the previous payload — versus `meal_food_analysis`, created specifically to escape that), a `status` column that couldn't express "accepted but not `nutrition_ready`", object keys that could be silently aliased on thumbnail failure, and 13 cherry-picked EXIF columns out of the ~25 the extractor produces. The current design fixes each of those in one pass — full rationale and the SOLID mapping behind it lives in the header comments of `0001_baseline.sql`, which are extensive by design.

### `users`

| Column | Notes |
|--------|-------|
| `user_id` | Primary key, `BIGSERIAL`. Stays an integer deliberately — it's embedded in the JWT `sub` claim as `str(user_id)`. |
| `user_email` | `UNIQUE`, `CHECK (user_email = lower(user_email))` |
| `daily_caloric_target` | `CHECK (BETWEEN 500 AND 10000)`, mirroring the API's own bounds |
| `timezone` | IANA name, e.g. `'America/Toronto'`. NULL = unknown. Validated at the API layer (`users.py`) against `zoneinfo` before it ever reaches a query — an invalid value would otherwise raise inside `v_meal_local_time`'s `AT TIME ZONE` expression and break that user's entire meal list. |

### `meals`

Renamed from `meal_uploads`. Holds identity and storage lifecycle only — no object keys, no analysis verdict.

| Column | Notes |
|--------|-------|
| `lifecycle` | `'pending'` → `'stored'` \| `'failed'`. Storage-only; says nothing about photo quality. |
| `failure_reason` | Set only when `lifecycle = 'failed'` (CHECK-enforced). Operator-facing, never shown to a user. |
| `captured_at_local` | `TIMESTAMP` **without** a time zone, deliberately — EXIF's wall-clock reading has no offset attached. |
| `captured_at_offset_minutes` | Set only when a real UTC offset is known. Storing the offset, not a derived UTC instant, keeps strictly more information. |
| `stored_at` | Set when `lifecycle` becomes `'stored'` (CHECK-enforced). |

### `meal_images`

One row per stored variant (`role IN ('original', 'thumbnail')`, unique per meal). Replaces `meal_uploads.image_url` / `.thumbnail_url`.

| Column | Notes |
|--------|-------|
| `object_key` | `NOT NULL`. Cannot be recomputed from `(user_id, meal_id)` — the extension comes from content-type or the client's filename — so it is stored, never inferred. |
| `content_type`, `image_format` | Distinct: the former is the MIME type, the latter Pillow's format string (`'JPEG'`). `image_format` is load-bearing — it feeds the Log card title. |
| `width`, `height` | Per variant, measured from the bytes. |
| `sha256` | `CHECK`-validated as a real hex-64 hash. Not `UNIQUE` — whether a duplicate upload is the same meal is a product decision, not a constraint. |

A failed thumbnail means **no row**, not a row pointing at the original's key. `has_thumbnail` on the API response reflects that directly.

### `meal_image_exif`

`(meal_id PRIMARY KEY, has_exif BOOLEAN, exif JSONB)`. The entire `extract_image_metadata()` output is stored, including GPS — nothing is silently discarded the way the old 13-column `image_metadata` table discarded most of it. A handful of known-large binary tags are pruned first (see Step 2 above).

### `analysis_stages`, `analysis_runs`, `analysis_artifacts`

Replaces **both** `image_qualities` and `meal_food_analysis`. The quality gate is no longer a special case — `technical_quality` and `vision_quality` are two stages like any other.

- `analysis_stages` is a lookup table (`stage`, `is_model_stage`, `sort_order`) seeded with all seven known stages, four of which have no code behind them yet. Adding a stage is an `INSERT`, not a migration.
- `analysis_runs` is one row per pipeline invocation (`trigger IN ('upload', 'reanalysis')`, `status IN ('running', 'succeeded', 'degraded', 'failed')`). Re-analysis is a new run, never an overwrite.
- `analysis_artifacts` is one row per `(run, stage)`: `payload` JSONB, `status IN ('ok', 'error', 'skipped')`, plus provenance columns nothing recorded before — `model_id`, `prompt_version`, `config_hash`, `latency_ms`.

`latency_ms` is the number that decides the sync-to-async switch documented in `PLANS.txt`; it's now measured from the first upload rather than something to reconstruct after the fact.

### `meal_gate_verdicts`

A full column-per-field projection of `quality_decision.QualityDecision` — all nine fields, one row per run. Three `CHECK` constraints pin the invariants `evaluate_quality()` already guarantees in Python (`accepted ⟺ usability_status = 'usable'`, `rejected ⟹ message present`, `nutrition_ready ⟺ no blocked reason`), so a future refactor that desyncs them fails at the write instead of shipping an incoherent verdict silently.

### `meal_foods`

One row per identified food for a run — a **derived projection** of the `visible_foods` artifact, not a second source of truth. `label_norm` is a generated column (`lower(btrim(label))`), indexed, and is the join key Phase 2's USDA lookup and any later avoid-list check will use.

### Views — the read contract

| View | Serves |
|------|--------|
| `v_meal_list` | `GET /api/meals`. Derives `status` from lifecycle + verdict, `nutrition_ready`, `has_original`/`has_thumbnail`, `likely_meal_type`. |
| `v_meal_detail` | `GET /api/meals/{id}`. `v_meal_list` plus the full verdict and a JSON-aggregated `foods` array. |
| `v_meal_latest_run` | The newest run per meal — what makes "latest coherent set" exact instead of timestamp-inferred. |
| `v_meal_local_time`, `v_meal_derived_context` | The meal-type derivation described in Step 8 above. |
| `v_analysis_stage_status` | Per-stage outcome for a meal's latest run. Debugging surface, not a product one. |

No API handler reads a table directly for a meal list or detail — only these views. `CREATE OR REPLACE VIEW` cannot reshape a column (name/type/position); reshaping one requires a migration that drops it and its dependents first, in the order documented at the top of the views section in `0001_baseline.sql`.

---

## Key source files

| File | Role |
|------|------|
| `app/main.py` | HTTP routes, upload validation |
| `app/meals.py` | Upload orchestration — the three-transaction sequence, response mapping. Zero SQL. |
| `app/users.py` | User service — request/response models, password hashing, timezone validation. Zero SQL. |
| `app/repositories/base.py` | `tx()` — the one transaction-boundary primitive every repository function assumes |
| `app/repositories/read_models.py` | Pydantic models mirroring the views, non-Optional wherever the view guarantees `NOT NULL` |
| `app/repositories/{users,meals,images,analysis}.py` | Every SQL statement in the app |
| `app/image_metadata.py` | EXIF extraction |
| `app/storage.py` | R2 upload, fetch, proxy path construction (`UploadedAssets` / `ImageAsset`) |
| `app/image_quality.py` | OpenCV technical checks, plus `analyzer_config_hash()` for provenance |
| `app/quality_decision.py` | Accept/reject gating (`DECISION_RULES_VERSION`) |
| `app/graph/builder.py` | LangGraph compile + `run_image_quality_graph()` (`PIPELINE_VERSION`) |
| `app/graph/nodes.py` | `image_quality_node` — Claude API call (`MODEL`, `PROMPT_VERSION`) |
| `app/graph/schema.py` | Structured output schema + system prompt |
| `app/graph/state.py` | `ImageQualityState` TypedDict |
| `app/auth.py` | JWT issue/verify |
| `app/db.py` | Connection pool (`get_connection()`) and `connect_direct()` for scripts |
| `app/migrate.py` | Migration runner (`python migrate.py`) |
| `app/migrations/*.sql` | All DDL — single source of truth |
| `app/scripts/reset_dev_db.{sql,py}` | Destructive dev-only schema reset — deliberately **not** a migration |
| `app/tests/` | pytest suite: pure-function tests always run; DB tests need `TEST_DATABASE_URL` |
| `frontend/src/pages/Scan.tsx` | Upload UI |
| `frontend/src/pages/Log.tsx` | Meal history UI |

---

## Environment & local dev

Copy `app/.env.example` → `app/.env` and fill in:

| Variable | Purpose |
|----------|---------|
| `DATABASE_URL` | Neon Postgres connection string |
| `JWT_SECRET` | Signs access tokens |
| `ANTHROPIC_API_KEY` | Claude vision node |
| `R2_*` | Cloudflare R2 object storage |
| `USDA_API_KEY` | Reserved for future nutrition lookup |
| `DB_POOL_MAX_SIZE`, `DB_POOL_MIN_SIZE` | Optional; override the connection pool's bounds (defaults: 5 max, 0 min) |
| `TEST_DATABASE_URL` | A **separate** Postgres database for the DB-backed test suite. Never point this at `DATABASE_URL` — the fixture that provisions it runs `DROP SCHEMA public CASCADE`. |

### Database setup

All DDL lives in `app/migrations/`. From `app/`, with `DATABASE_URL` set:

```bash
python migrate.py --status   # what's applied, what's pending
python migrate.py            # apply everything pending
```

Migrations are forward-only and each runs in its own transaction.

**Resetting the dev database.** Needed occasionally in development, and needed once to move onto the current schema (the earlier one was reconstructed from code with no committed DDL at all). This is destructive and deliberately lives outside `migrations/` so no migration file in the repo is capable of dropping data:

```bash
# with psql:
psql "$DATABASE_URL" -f scripts/reset_dev_db.sql
python migrate.py

# without psql:
python scripts/reset_dev_db.py           # dry run, prints the target host/db
python scripts/reset_dev_db.py --yes     # actually drops and recreates public
python migrate.py
```

`meal_id` restarts from 1 after a reset, and R2 object keys embed it — **purge the bucket's `users/` prefix in the same step**, or a new meal 1 will collide with the old meal 1's object and serve a stale image.

**Setting up a test database.** The DB-backed test suite needs `TEST_DATABASE_URL` pointed at something that is not the real database — a local `postgres:16` container, a Neon branch (`neonctl branches create`), or a second database on the same Neon project (`CREATE DATABASE platter_test`, then swap the database name in the connection string). Whichever you use, connect to it directly rather than through a `-pooler` hostname when running ad-hoc scripts against it: a session-level `SET` on a PgBouncer transaction-pooled connection can leak onto whatever backend the pooler hands to the next client. `psycopg_pool` connections from the app itself set `prepare_threshold=None` specifically to avoid the pooler's other sharp edge (server-side prepared statements do not survive being handed to a different backend).

### Dedicated Neon test branch

The shared test target is the isolated Neon branch `platter-test`, database
`platter_test`. It is disposable: the test fixture runs `DROP SCHEMA public
CASCADE` before applying migrations.

With Neon CLI authenticated and this workspace linked, run the full suite from
the repository root:

```powershell
powershell -ExecutionPolicy Bypass -File .\app\scripts\run_test_db.ps1
```

The helper retrieves the direct branch-specific connection string at runtime,
sets `TEST_DATABASE_URL` only for the test process, then removes it. It never
stores a password in a file or in Git. If the branch is deliberately deleted,
recreate it with:

```powershell
npx.cmd -y neonctl@latest branches create --name platter-test --parent production --schema-only --no-secrets
```

When obtaining a URL manually, select database `platter_test` and the direct
endpoint, not a `-pooler` hostname.

### Run locally

**Backend** (from `app/`):

```bash
uvicorn main:app --reload
# -> http://127.0.0.1:8000/docs
```

**Tests** (from `app/`):

```bash
pip install -r requirements.txt -r requirements-dev.txt
python -m pytest
```

Pure-function tests (`test_quality_decision.py`) always run. The DB-backed tests (`test_migrations.py`, `test_constraints.py`, `test_views.py`, `test_meals_repo.py`, `test_upload_flow.py`) skip automatically unless `TEST_DATABASE_URL` is set — R2 and the Anthropic API are monkeypatched inside them, so they need no cloud credentials beyond the test database itself.

**Frontend** (from `frontend/`):

```bash
npm run dev
# -> http://localhost:5173
```

**Docker Compose** (repo root):

```bash
docker compose up
# backend :8000, frontend :8080
```

CORS allows `localhost:5173`, `localhost:8080`, and `useplatter.ca`.

---

## Planned work

These are design notes from earlier docs and code comments — **not implemented**.

**`PLANS.txt` at the repo root is the phased build plan** and supersedes this section where they disagree. `docs/AnalysisPipeline.md` holds the detailed design for the analysis stages. `docs/Vision.md` is the product north star and does not change what is implemented here.

### Near term

- User login, UI, and persistent Postgres — **done**
- Migrations, baseline DDL, analysis run/artifact model, repositories, DB test scaffolding — **done**
- Visual understanding → nutrition (Phases 1–2) — **next**

### Nutrition analysis pipeline (future LangGraph nodes)

The graph in `app/graph/builder.py` is scaffolded for additional nodes after `image_quality`. Planned stages (full design in `docs/AnalysisPipeline.md`):

**Step 1 — Visual understanding layer**

Ask an LLM broad questions about the full image:

- Visible foods, likely hidden ingredients, cooking methods
- Food relationships, context clues, uncertainties
- Infers things segmentation alone cannot

**Step 2 — Segmentation layer**

Structured regional output per food item:

- `region_id`, `region_name`, `mask`, `bbox`
- `plate_coverage_percent`, `occlusion_level`

**Downstream (not started)**

- Portion sizing from regions + plate reference
- Calorie and macro estimation
- USDA FoodData Central lookup (`USDA_API_KEY` already in `.env.example`)

### Other gaps

| Item | Notes |
|------|-------|
| Async analysis | Today the client waits for Claude. Deliberately deferred — see the sync/async decision and its switch triggers in `PLANS.txt`. `analysis_artifacts.latency_ms` now measures the number that would trigger the switch. |
| Geocoding | GPS coordinates are persisted inside `meal_image_exif.exif`; reverse geocoding into a city/country is not wired |
| K8S removal | `k8s/` and `cluster.yml` still present; migration to a simpler deploy is Phase 4 |
| Multiple upload sources | Only `"web_upload"` exists in `meal_sources`; mobile/camera API sources not built |

### Extending the graph and the analysis model

To add a new analysis stage:

1. `INSERT` the stage into `analysis_stages` (a migration, but a tiny one — no `ALTER TABLE`)
2. Define state fields in `app/graph/state.py`
3. Add a node in `app/graph/nodes.py`
4. Wire edges in `app/graph/builder.py` (`image_quality` → new node → …)
5. Call `analysis_repo.insert_artifact()` for it inside `meals.run_meal_analysis()` / the T3 block in `create_meal_with_metadata()`

No new table is needed for a new stage's raw output — `analysis_artifacts` already has a row for it. A new table is only justified when the stage's output needs to be **queried relationally** (the way `meal_foods` exists so Phase 2's USDA join and Discover's "recent labels" query are real SQL rather than JSON-path digging).

The quality node already collects signals (`portion_difficulty`, `food_overlap_level`, etc.) meant to inform downstream estimation — those fields are stored but not yet consumed by later stages.

---

## Quick reference — rejection messages

| Trigger | User message |
|---------|--------------|
| Not food | "We couldn't find a meal in this photo. Please upload a clear photo of your food." |
| Blur | "The photo looks too blurry. Try retaking it in focus." |
| Underexposure | "The photo is too dark. Try retaking it with more light." |
| Overexposure | "The photo is too bright. Try retaking it with less glare." |
| Brightness | "The lighting makes the meal hard to see. Try even, natural light." |
| Resolution | "The photo's resolution is too low. Upload a larger, clearer image." |
| Vision reject/retake | "This photo isn't clear enough to analyze your meal. Please try another photo." |

Multiple triggers are joined into one message (deduplicated).
