-- The per-day ceiling on Workers AI calls, counted at each call in AIProxy (src/aigateway.ts).
-- model_budget counts public questions; this counts the model calls they make, so a retry loop or a
-- misbehaving container cannot spend past DAILY_AI_CALLS in a day.
CREATE TABLE IF NOT EXISTS ai_call_budget (
  day   TEXT PRIMARY KEY,
  calls INTEGER NOT NULL
);
