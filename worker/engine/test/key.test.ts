// The Worker's key, cleaned question and salient terms must match the Python engine on every shared
// vector (config/cache_key_vectors.json, written by scripts/v2/make_cache_vectors.py).
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { STOPWORDS } from "../src/config";
import { canonicalFilters, cleanQuestion, contentKey, normalizeQuestion, restoreTerms, salientTerms } from "../src/key";

interface Vector {
  name: string;
  question: string;
  filters: Record<string, unknown> | null;
  normalized_question: string;
  canonical_filters: Record<string, string>;
  key: string;
  clean_question: string;
  salient_terms: string[];
}

const file = fileURLToPath(new URL("../../../config/cache_key_vectors.json", import.meta.url));
const shared = JSON.parse(readFileSync(file, "utf-8")) as { key_version: number; context: string; vectors: Vector[] };

describe("shared vectors with the Python engine", () => {
  it("has vectors for the current key version", () => {
    expect(shared.key_version).toBe(2);
    expect(shared.vectors.length).toBeGreaterThan(20);
  });

  for (const v of shared.vectors) {
    it(v.name, async () => {
      expect(normalizeQuestion(v.question)).toBe(v.normalized_question);
      expect(canonicalFilters(v.filters)).toEqual(v.canonical_filters);
      expect(await contentKey(shared.context, v.question, v.filters)).toBe(v.key);
      expect(cleanQuestion(v.question)).toBe(v.clean_question);
      expect(salientTerms(cleanQuestion(v.question), STOPWORDS)).toEqual(v.salient_terms);
    });
  }
});

describe("terms withheld from a visitor's row", () => {
  it("restores them from the asker's question", () => {
    const response = { answer: { coverage: { n_passages: 3, terms_withheld: { salient_count: 3, uncovered_index: [2] } } } };
    expect(restoreTerms(response, ["tobacco", "ontario", "1985"])).toBe(true);
    expect(response.answer.coverage).toEqual({ n_passages: 3, salient_terms: ["tobacco", "ontario", "1985"], uncovered_terms: ["1985"] });
  });

  it("refuses a count that does not match", () => {
    const response = { answer: { coverage: { terms_withheld: { salient_count: 2, uncovered_index: [] } } } };
    expect(restoreTerms(response, ["one"])).toBe(false);
    expect(response.answer.coverage.terms_withheld).toBeDefined();
  });

  it("leaves a curated row alone", () => {
    const response = { answer: { coverage: { salient_terms: ["a"], uncovered_terms: [] } } };
    expect(restoreTerms(response, ["something", "else"])).toBe(true);
    expect(response.answer.coverage.salient_terms).toEqual(["a"]);
  });
});

describe("filters the Worker cannot key", () => {
  it("returns null for a min_ocr that is not a number", async () => {
    expect(canonicalFilters({ min_ocr: "high" })).toBeNull();
    expect(await contentKey("c", "q", { min_ocr: "high" })).toBeNull();
  });
});
