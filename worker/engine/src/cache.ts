// The answer cache in D1 (format v2, docs/v2/formats/answer_cache.md): the Worker reads it before
// waking the engine, and the engine reads and writes it through the CacheProxy entrypoint.
import { ENGINE_CONFIG, STOPWORDS, type AnswerNote } from "./config";
import { cleanQuestion, contentKey, restoreTerms, salientTerms, type Filters } from "./key";

export const COLUMNS = [
  "key", "scope", "curated", "question", "response_json", "extras_version", "model",
  "prompt_sha256", "context", "created_at", "expires_at",
] as const;

export type CacheRow = Record<(typeof COLUMNS)[number], string | number | null>;

const KEY_PATTERN = /^[0-9a-f]{64}$/;

export function isKey(value: string): boolean {
  return KEY_PATTERN.test(value);
}

/** A row that has not expired, or null. */
export async function readRow(db: D1Database, key: string, now: Date = new Date()): Promise<CacheRow | null> {
  return db
    .prepare(`SELECT ${COLUMNS.join(", ")} FROM answers_v2 WHERE key = ? AND (expires_at IS NULL OR expires_at >= ?)`)
    .bind(key, isoSeconds(now))
    .first<CacheRow>();
}

/** Store a row written by the engine. Only well-formed rows are accepted, and a row that is not
 *  curated must carry no question and an expiry. */
export async function writeRow(db: D1Database, row: CacheRow): Promise<void> {
  for (const column of COLUMNS) {
    if (!(column in row)) throw new Error(`cache row is missing ${column}`);
  }
  if (!isKey(String(row.key))) throw new Error("cache row key is not a sha256 hex string");
  if (!row.curated && (row.question !== null || row.expires_at === null)) {
    throw new Error("a row that is not curated must have no question and an expiry");
  }
  await db
    .prepare(`INSERT OR REPLACE INTO answers_v2 (${COLUMNS.join(", ")}) VALUES (${COLUMNS.map(() => "?").join(", ")})`)
    .bind(...COLUMNS.map((c) => row[c]))
    .run();
}

/** Delete expired rows (the daily cron). Returns how many went. */
export async function purgeExpired(db: D1Database, now: Date = new Date()): Promise<number> {
  const result = await db
    .prepare("DELETE FROM answers_v2 WHERE expires_at IS NOT NULL AND expires_at < ?")
    .bind(isoSeconds(now))
    .run();
  return result.meta.changes ?? 0;
}

export function isoSeconds(date: Date): string {
  return date.toISOString().replace(/\.\d{3}Z$/, "+00:00");
}

/** Dated editorial notes about a stored answer asked with exactly this question in this scope. */
export function notesForAnswer(scope: string, question: string, cached: boolean): Omit<AnswerNote, "target">[] {
  return ENGINE_CONFIG.answer_notes
    .filter((n) => n.target.scope === scope && n.target.question === question && (cached || !n.target.cached_only))
    .map(({ id, date, text, reason }) => ({ id, date, text, reason }))
    .sort((a, b) => (a.date === b.date ? a.id.localeCompare(b.id) : a.date.localeCompare(b.date)));
}

export interface AskInput {
  scope: string;
  question: string;
  filters: Filters;
}

/** The stored answer for a question, ready to serve exactly as the engine serves a cache hit, or
 *  null when the Worker cannot serve it (no row, an older extras version, terms that do not
 *  restore). A null always means: forward to the engine. */
export async function servedHit(db: D1Database, input: AskInput): Promise<Record<string, unknown> | null> {
  const scope = ENGINE_CONFIG.scopes[input.scope];
  if (!scope) return null;
  const key = await contentKey(scope.context, input.question, input.filters);
  if (key === null) return null;
  const row = await readRow(db, key);
  if (!row || row.extras_version !== ENGINE_CONFIG.extras_version) return null;
  const response = JSON.parse(String(row.response_json)) as Record<string, any>;
  if (!restoreTerms(response, salientTerms(cleanQuestion(input.question), STOPWORDS))) return null;
  response.answer = { ...response.answer, cached: { created_at: row.created_at } };
  response.editorial_notes = notesForAnswer(input.scope, input.question, true);
  return response;
}
