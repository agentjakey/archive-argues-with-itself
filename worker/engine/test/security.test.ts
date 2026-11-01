// Security fixtures for the engine Worker, run locally against fakes (never production): D1 cache
// poisoning, the stub path and nocache. The stub and nocache rules for production and staging are
// also covered in worker.test.ts ("reading an /ask request", "nocache from the public"); the engine
// side is in tests/test_security_fixtures.py.
import { describe, expect, it } from "vitest";
import { readAsk } from "../src/ask";
import { servedHit, writeRow, type CacheRow } from "../src/cache";
import { ENGINE_CONFIG } from "../src/config";
import { cleanQuestion, contentKey, normalizeQuestion } from "../src/key";
import { fakeEnv } from "./fakes";

const PILOT = ENGINE_CONFIG.scopes.pilot;
const MICROLOG = ENGINE_CONFIG.scopes.microlog;

function row(key: string, context: string, text: string, overrides: Partial<CacheRow> = {}): CacheRow {
  return {
    key, scope: "pilot", curated: 1, question: "tobacco",
    response_json: JSON.stringify({ answer: { text, abstained: false, coverage: {} }, evidence: [], flagged: null }),
    extras_version: ENGINE_CONFIG.extras_version, model: PILOT.model, prompt_sha256: "p", context,
    created_at: "2026-10-31T12:00:00+00:00", expires_at: null, ...overrides,
  };
}

describe("D1 cache poisoning", () => {
  it("never serves one collection's stored answer for the same question in another", async () => {
    const env = fakeEnv();
    const key = (await contentKey(PILOT.context, "tobacco", {})) as string;
    await writeRow(env.DB, row(key, PILOT.context, "pilot answer"));
    expect(await servedHit(env.DB, { scope: "pilot", question: "tobacco", filters: {} })).not.toBeNull();
    expect(await servedHit(env.DB, { scope: "microlog", question: "tobacco", filters: {} })).toBeNull();
    expect(MICROLOG.context).not.toBe(PILOT.context);
  });

  it("never serves an answer stored under another provider's context, such as the stub's on staging", async () => {
    const env = fakeEnv();
    const stubContext = "stub-context-of-a-staging-run";
    const key = (await contentKey(stubContext, "tobacco", {})) as string;
    await writeRow(env.DB, row(key, stubContext, "stub answer"));
    expect(await servedHit(env.DB, { scope: "pilot", question: "tobacco", filters: {} })).toBeNull();
  });

  it("keys a padded filter like the clean one, so the engine must answer with the clean value", async () => {
    // The engine now applies filters exactly as the key sees them (api/cache.py applied_filters);
    // before, " ontario " shared this key but matched nothing, and the empty answer was served here.
    const clean = await contentKey(PILOT.context, "tobacco", { jurisdiction: "ontario" });
    const padded = await contentKey(PILOT.context, "tobacco", { jurisdiction: "  ontario " });
    expect(padded).toBe(clean);
    expect(await contentKey(PILOT.context, "tobacco", { jurisdiction: "Ontario" })).not.toBe(clean);
    expect(await contentKey(PILOT.context, "tobacco", { min_ocr: "high" })).toBeNull();   // forwarded, never keyed
  });

  it("gives two questions one key only when the engine cleans them to the same question", async () => {
    const variants = [
      ["tobacco control", "tobacco  control", " tobacco control ", "tobacco\tcontrol", "tobacco\r\ncontrol",
       "tobacco\u0000control", "tobacco\u001fcontrol"],
      ["tobacco\u00a0control", "tobacco\u2003control"],          // Unicode spaces: keyed apart, cleaned alike
      ["tobacco\u200bcontrol"],                                  // zero-width space: a different word
    ];
    const all = variants.flat();
    for (const a of all) {
      for (const b of all) {
        const sameKey = (await contentKey(PILOT.context, a, {})) === (await contentKey(PILOT.context, b, {}));
        if (sameKey) expect(cleanQuestion(a)).toBe(cleanQuestion(b));
      }
    }
    expect(normalizeQuestion("tobacco\u00a0control")).not.toBe(normalizeQuestion("tobacco control"));
  });

  it("refuses rows the engine could be tricked into writing: a bad key, a visitor row with its question, no expiry", async () => {
    const env = fakeEnv();
    const key = (await contentKey(PILOT.context, "tobacco", {})) as string;
    await expect(writeRow(env.DB, row("not-a-key", PILOT.context, "x"))).rejects.toThrow();
    await expect(writeRow(env.DB, row(key, PILOT.context, "x", { curated: 0, expires_at: "2099-01-01T00:00:00+00:00" }))).rejects.toThrow();
    await expect(writeRow(env.DB, row(key, PILOT.context, "x", { curated: 0, question: null, expires_at: null }))).rejects.toThrow();
  });
});

describe("the stub path and nocache from the public", () => {
  const production = { PUBLIC_MODELS: "", PUBLIC_NOCACHE: "" };
  const staging = { PUBLIC_MODELS: "stub", PUBLIC_NOCACHE: "true" };
  const post = (body: Record<string, unknown>) =>
    new Request("https://api.test/ask?scope=pilot", { method: "POST", body: JSON.stringify(body) });

  it("refuses the stub however it is asked for in production", async () => {
    for (const request of [
      post({ question: "q", provider: "stub" }),
      post({ question: "q", provider: "stub", model: PILOT.model }),
      post({ question: "q", provider: "STUB" }),
      new Request("https://api.test/ask?q=t&provider=stub&scope=microlog"),
    ]) {
      expect((await readAsk(request, production))?.allowed).toBe(false);
    }
  });

  it("on staging, a stub answer is never read from the stored answers", async () => {
    const parsed = await readAsk(post({ question: "tobacco", provider: "stub" }), staging);
    expect(parsed).toMatchObject({ allowed: true, cacheable: false });
  });

  it("a public nocache in production is dropped, so it cannot be used to force model calls past the cache", async () => {
    const parsed = await readAsk(post({ question: "tobacco", nocache: 1 }), production);
    expect(parsed).toMatchObject({ cacheable: true, nocacheDropped: true });
  });
});
