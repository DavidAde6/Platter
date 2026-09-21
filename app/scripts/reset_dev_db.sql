-- DESTRUCTIVE. DEV ONLY.
--
-- Drops every object in the public schema, including schema_migrations, so
-- that `python migrate.py` re-provisions from 0001 with no orphan version
-- rows left behind.
--
-- Deliberately NOT in migrations/. Nothing the migration runner can apply
-- should be capable of destroying data; a mis-set DATABASE_URL would then be
-- a lost database rather than an error. Running this has to be a choice.
--
-- Requires psql:
--     psql "$DATABASE_URL" -f scripts/reset_dev_db.sql
--
-- No psql installed? Use the Python equivalent, which also prints the target
-- host and refuses without --yes:
--     python scripts/reset_dev_db.py --yes
--
-- Remember to purge the R2 `users/` prefix as well. meal_id restarts at 1 and
-- object keys embed it, so a new meal 1 would otherwise collide with the old
-- meal 1's object and serve a stale image.

DROP SCHEMA public CASCADE;
CREATE SCHEMA public;
