// The release's data shards (docs/formats/site_data.md): fetched on demand, once, and cached for
// the page's lifetime. They hold everything that does not depend on a visitor's own question, so
// the reading room works with the engine asleep or down.
import type { AskResponse, CoverageResponse, Example, Filters, Health, ScopesResponse, Story } from "../types";
import { STATIC_DATA } from "./config";
import { canonicalFilters, normalizeQuestion, sameFilters } from "./curated";

interface IndexEntry {
  label: string;
  question: string;
  normalized_question: string;
  filters: Record<string, string>;
  file: string | null;
  coverage?: string | null;
}

interface AnswerIndex {
  format_version: number;
  scope: string;
  answers: IndexEntry[];
}

const loaded = new Map<string, Promise<unknown>>();

async function shard<T>(path: string): Promise<T> {
  const url = `${STATIC_DATA}/${path}`;
  let pending = loaded.get(url);
  if (!pending) {
    pending = fetch(url, { headers: { accept: "application/json" } }).then((resp) => {
      if (!resp.ok) throw new Error(`shard ${path}: status ${resp.status}`);
      return resp.json();
    });
    pending.catch(() => loaded.delete(url));   // a failed fetch may be retried later
    loaded.set(url, pending);
  }
  return pending as Promise<T>;
}

export const scopes = () => shard<ScopesResponse>("scopes.json");
export const examples = (scope: string) => shard<Example[]>(`${scope}/examples.json`);
export const stories = (scope: string) => shard<Story[]>(`${scope}/stories.json`);
export const health = (scope: string) =>
  shard<Omit<Health, "status">>(`${scope}/health.json`).then((h) => ({ ...h, status: "ok" as const }));

async function findCurated(scope: string, question: string, filters: Filters | undefined): Promise<IndexEntry | null> {
  let index: AnswerIndex;
  try {
    index = await shard<AnswerIndex>(`${scope}/answers/index.json`);
  } catch {
    return null;
  }
  const wanted = normalizeQuestion(question);
  const wantedFilters = canonicalFilters(filters ?? {});
  return (
    index.answers.find((e) => e.normalized_question === wanted && sameFilters(e.filters, wantedFilters)) ?? null
  );
}

/** The recorded answer for a seed or story question, or null when the question is not one or has
 *  no recorded answer (then the engine answers it). */
export async function recordedAnswer(scope: string, question: string, filters: Filters | undefined): Promise<AskResponse | null> {
  const entry = await findCurated(scope, question, filters);
  if (!entry || !entry.file) return null;
  try {
    return await shard<AskResponse>(`${scope}/${entry.file}`);
  } catch {
    return null;
  }
}

/** The recorded coverage for a seed or story question, or null. */
export async function recordedCoverage(scope: string, question: string, filters: Filters | undefined): Promise<CoverageResponse | null> {
  const entry = await findCurated(scope, question, filters);
  if (!entry || !entry.coverage) return null;
  try {
    return await shard<CoverageResponse>(`${scope}/${entry.coverage}`);
  } catch {
    return null;
  }
}
