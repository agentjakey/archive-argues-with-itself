// Plain names for the parts of the whole collection: a collection's own label, or a shard id
// ("federal-1899-1911", "unknown-1861-1993") read as its place and years.
import type { ScopeInfo } from "../types";

function capitalize(word: string): string {
  return word ? word[0].toUpperCase() + word.slice(1) : word;
}

export function partLabel(id: string, scopes: ScopeInfo[] | null | undefined): string {
  const known = scopes?.find((s) => s.name === id);
  if (known) return known.label;
  const m = /^([a-z_]+)-(\d{4})-(\d{4})$/.exec(id);
  if (m) {
    const place = m[1] === "unknown" ? "Place unknown" : m[1].split("_").map(capitalize).join(" ");
    return `${place}, ${m[2]} to ${m[3]}`;
  }
  return id;
}

/** "A", "A and B", "A, B and C". */
export function listWords(items: string[]): string {
  if (items.length <= 1) return items.join("");
  return `${items.slice(0, -1).join(", ")} and ${items[items.length - 1]}`;
}

/** The engine router's reason for leaving a part out, in plain words. */
const REASONS: Record<string, string> = {
  "other jurisdictions": "it covers other places than the one asked about",
  "no documents in the period": "it has no documents from the years asked about",
  "none of the question's words occur in it": "none of the question's words occur in it",
  "ranked below the engines woken": "other parts hold more of the question's words; each question searches the closest few",
  "not in the router index yet": "it has just been added and is not searchable together with the others yet",
  "its engine did not answer": "it did not answer in time",
};

export function reasonWords(reason: string | undefined): string {
  if (!reason) return "not searched for this question";
  return REASONS[reason] ?? reason;
}
