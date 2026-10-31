-- Visitor rows are kept for 90 days, not 180 (2026-10-31). Rows written before the change expire
-- 90 days after they were written; curated rows (expires_at NULL) are untouched.
UPDATE answers_v2
SET expires_at = strftime('%Y-%m-%dT%H:%M:%S+00:00', created_at, '+90 days')
WHERE curated = 0
  AND expires_at IS NOT NULL
  AND expires_at > strftime('%Y-%m-%dT%H:%M:%S+00:00', created_at, '+90 days');
