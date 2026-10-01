-- M1: expose the latest coherent visible-food run through typed read models.
CREATE OR REPLACE VIEW v_meal_list AS
SELECT m.meal_id, m.user_id, m.source, m.created_at, m.lifecycle,
       orig.image_format, orig.width, orig.height,
       (orig.image_id IS NOT NULL) AS has_original,
       (thumb.image_id IS NOT NULL) AS has_thumbnail,
       CASE WHEN m.lifecycle = 'failed' THEN 'rejected'
            WHEN m.lifecycle = 'pending' THEN 'processing'
            WHEN v.accepted IS NULL THEN 'processing'
            WHEN v.accepted THEN 'completed' ELSE 'rejected' END AS status,
       COALESCE(v.nutrition_ready, FALSE) AS nutrition_ready,
       v.nutrition_blocked_reason, v.message AS rejection_reason,
       dc.likely_meal_type, dc.meal_time_source, r.finished_at AS processed_at,
       CASE WHEN v.accepted IS NOT TRUE THEN 'not_applicable'
            WHEN visible.status = 'ok' AND visible.payload->>'result' = 'identified' THEN 'available'
            ELSE 'unavailable' END AS food_analysis_status,
       COALESCE(labels.food_labels, ARRAY[]::text[]) AS food_labels
FROM meals m
LEFT JOIN meal_images orig ON orig.meal_id = m.meal_id AND orig.role = 'original'
LEFT JOIN meal_images thumb ON thumb.meal_id = m.meal_id AND thumb.role = 'thumbnail'
LEFT JOIN v_meal_latest_run r ON r.meal_id = m.meal_id
LEFT JOIN meal_gate_verdicts v ON v.run_id = r.run_id
LEFT JOIN v_meal_derived_context dc ON dc.meal_id = m.meal_id
LEFT JOIN analysis_artifacts visible ON visible.run_id = r.run_id AND visible.stage = 'visible_foods'
LEFT JOIN LATERAL (
    SELECT array_agg(mf.label ORDER BY mf.ordinal) AS food_labels
    FROM meal_foods mf WHERE mf.run_id = r.run_id
) labels ON TRUE;

CREATE OR REPLACE VIEW v_meal_detail AS
-- Keep the pre-M1 output columns in their existing positions. PostgreSQL
-- permits CREATE OR REPLACE VIEW to append columns, but not to slide these
-- fields after the new columns that v_meal_list gains.
SELECT l.meal_id, l.user_id, l.source, l.created_at, l.lifecycle,
       l.image_format, l.width, l.height, l.has_original, l.has_thumbnail,
       l.status, l.nutrition_ready, l.nutrition_blocked_reason,
       l.rejection_reason, l.likely_meal_type,
       l.meal_time_source, l.processed_at,
       r.run_id, r.pipeline_version, r.status AS run_status,
       v.usability_status, v.recommended_action, v.is_food_image,
       v.food_confidence, v.analysis_complete, v.rules_version,
       COALESCE(f.foods, '[]'::json) AS foods,
       l.food_analysis_status, l.food_labels
FROM v_meal_list l
LEFT JOIN v_meal_latest_run r ON r.meal_id = l.meal_id
LEFT JOIN meal_gate_verdicts v ON v.run_id = r.run_id
LEFT JOIN LATERAL (
    SELECT json_agg(json_build_object('label', mf.label,
       'possible_types', mf.possible_types,
       'possible_preparations', mf.possible_preparations,
       'confidence', mf.confidence) ORDER BY mf.ordinal) AS foods
    FROM meal_foods mf WHERE mf.run_id = r.run_id
) f ON TRUE;
