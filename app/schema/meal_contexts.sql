-- Context inferred at upload time (1:1 with a meal). Populated by
-- create_meal_with_metadata() from the uploaded image's EXIF metadata.
CREATE TABLE IF NOT EXISTS meal_contexts (
    context_id        BIGSERIAL PRIMARY KEY,
    meal_id           BIGINT NOT NULL UNIQUE REFERENCES meal_uploads(meal_id) ON DELETE CASCADE,
    likely_meal_type  TEXT CHECK (likely_meal_type IN (
                          'breakfast', 'lunch', 'dinner', 'unknown'
                      )),
    city              TEXT,
    country           TEXT
);
