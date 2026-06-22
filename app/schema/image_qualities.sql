-- Image-quality analysis (1:1 with a meal). detected_issues is populated by
-- analyze_image_quality() at upload time; the remaining columns (is_food_image,
-- food_confidence, food_overlap_level, recommended_action, usability_status)
-- are reserved for the food-detection model.
CREATE TABLE IF NOT EXISTS image_qualities (
    quality_id          BIGSERIAL PRIMARY KEY,
    meal_id             BIGINT NOT NULL UNIQUE REFERENCES meal_uploads(meal_id) ON DELETE CASCADE,
    is_food_image       BOOLEAN,
    food_confidence     REAL CHECK (food_confidence >= 0 AND food_confidence <= 1),
    detected_issues     JSONB NOT NULL DEFAULT '{}'::jsonb,
    food_overlap_level  TEXT,
    recommended_action  TEXT,
    usability_status    TEXT
);
