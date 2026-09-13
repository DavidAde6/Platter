-- 0002 — Seed the lookup tables.
--
-- Separate from 0001 so that structure and reference data stay separable: a
-- future stage or upload source is appended here (or in a later migration) as
-- data, without touching a table definition.
--
-- Every INSERT is ON CONFLICT DO NOTHING. migrate.py will not re-run an
-- applied file, but idempotent seeds cost nothing and make the file safe to
-- replay by hand against a database in an unknown state.


-- ---------------------------------------------------------------------------
-- Where a meal record came from. 'web_upload' is the only value the code
-- produces today (it is hardcoded at the main.py call site).
-- ---------------------------------------------------------------------------
INSERT INTO meal_sources (source, description) VALUES
    ('web_upload', 'Uploaded through the web app')
ON CONFLICT (source) DO NOTHING;


-- ---------------------------------------------------------------------------
-- Stored image variants. Both are written on a successful upload; a failed
-- thumbnail simply means no 'thumbnail' row exists for that meal.
-- ---------------------------------------------------------------------------
INSERT INTO image_roles (role, description) VALUES
    ('original',  'The bytes as uploaded, in their original format'),
    ('thumbnail', 'Downscaled JPEG for list views (max edge 256px)')
ON CONFLICT (role) DO NOTHING;


-- ---------------------------------------------------------------------------
-- Pipeline stages.
--
-- Seeded ahead of implementation. Four of these seven have no code behind
-- them yet; the rows exist so that shipping the code is a code change only.
-- is_model_stage answers "may this stage call a model?", which is what makes
-- NULL model_id / prompt_version expected rather than suspicious.
--
-- Note what is NOT here: the gate decision. QualityDecision has its own typed
-- table (meal_gate_verdicts), and recording it as an artifact payload as well
-- would recreate exactly the duplication this schema removes — the old
-- image_qualities promoted is_food_image to a column while also writing the
-- whole decision into detected_issues["decision"].
-- ---------------------------------------------------------------------------
INSERT INTO analysis_stages (stage, description, is_model_stage, sort_order) VALUES
    ('technical_quality',
     'Deterministic OpenCV checks: blur, brightness, exposure, resolution',
     FALSE, 10),

    ('vision_quality',
     'VLM judgement of photo usability for calorie and macro estimation',
     TRUE, 20),

    ('quality_context',
     'Distilled constraints derived from the quality signals, for downstream prompts',
     FALSE, 30),

    ('visible_foods',
     'VLM identification of visible foods, with explicit ambiguity',
     TRUE, 40),

    ('segmentation',
     'Per-food regions and plate coverage for portion sizing',
     TRUE, 50),

    ('fused_analysis',
     'Deterministic reconciliation of semantic labels against spatial regions',
     FALSE, 60),

    ('nutrition',
     'USDA lookup and macro ranges; may fall back to a model estimate',
     TRUE, 70)
ON CONFLICT (stage) DO NOTHING;
