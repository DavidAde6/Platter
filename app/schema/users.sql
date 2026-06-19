-- Users table (already applied in Neon)
CREATE TABLE IF NOT EXISTS users (
    user_id              BIGSERIAL PRIMARY KEY,
    user_name            TEXT NOT NULL,
    user_email           TEXT NOT NULL UNIQUE,
    user_password_hash   TEXT NOT NULL,
    daily_caloric_target INTEGER,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS users_updated_at ON users;
CREATE TRIGGER users_updated_at
    BEFORE UPDATE ON users
    FOR EACH ROW
    EXECUTE FUNCTION set_updated_at();
