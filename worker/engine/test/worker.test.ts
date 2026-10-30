// Serving stored answers from D1, the guards, the budget, keep-warm windows and range parsing.
import { describe, expect, it } from "vitest";
import { readAsk } from "../src/ask";
import { notesForAnswer, purgeExpired, readRow, servedHit, writeRow, type CacheRow } from "../src/cache";
import { ENGINE_CONFIG } from "../src/config";
import { checkTurnstile, clientKey, corsHeaders, takeModelBudget, TURNSTILE_HEADER } from "../src/guard";
import { contentKey } from "../src/key";
import { parseRange } from "../src/ranges";
import { keepWarmNow, parseWindows } from "../src/schedule";
import { FakeD1, fakeEnv } from "./fakes";

const PILOT = ENGINE_CONFIG.scopes.pilot;

async function storedRow(question: string, overrides: Partial<CacheRow> = {}): Promise<CacheRow> {
  const key = (await contentKey(PILOT.context, question, {})) as string;
  const response = {
    answer: { text: "A stored answer.", abstained: false, coverage: { salient_terms: ["tobacco"], uncovered_terms: [] } },
    evidence: [{ passage_id: "item#1:0" }],
    flagged: null,
  };
  return {
    key, scope: "pilot", curated: 1, question, response_json: JSON.stringify(response),
    extras_version: ENGINE_CONFIG.extras_version, model: PILOT.model, prompt_sha256: "p", context: PILOT.context,
    created_at: "2026-10-16T12:00:00+00:00", expires_at: null, ...overrides,
  };
}

describe("serving a stored answer without the engine", () => {
  it("serves a curated row with its creation time", async () => {
    const env = fakeEnv();
    await writeRow(env.DB, await storedRow("tobacco"));
    const hit = await servedHit(env.DB, { scope: "pilot", question: "  tobacco ", filters: {} });
    expect(hit).not.toBeNull();
    expect((hit as any).answer.cached).toEqual({ created_at: "2026-10-16T12:00:00+00:00" });
    expect((hit as any).answer.text).toBe("A stored answer.");
    expect((hit as any).editorial_notes).toEqual([]);
  });

  it("restores a visitor row's terms and never serves an older extras version", async () => {
    const env = fakeEnv();
    const visitor = await storedRow("ontario tobacco control", {
      curated: 0, question: null, expires_at: "2099-01-01T00:00:00+00:00",
      response_json: JSON.stringify({ answer: { coverage: { terms_withheld: { salient_count: 3, uncovered_index: [0] } } }, evidence: [] }),
    });
    await writeRow(env.DB, visitor);
    const hit = (await servedHit(env.DB, { scope: "pilot", question: "ontario tobacco control", filters: {} })) as any;
    expect(hit.answer.coverage.salient_terms).toEqual(["ontario", "tobacco", "control"]);
    expect(hit.answer.coverage.uncovered_terms).toEqual(["ontario"]);
    await writeRow(env.DB, { ...visitor, extras_version: "older" });
    expect(await servedHit(env.DB, { scope: "pilot", question: "ontario tobacco control", filters: {} })).toBeNull();
  });

  it("attaches the dated note to the stored Alberta answer", async () => {
    const note = ENGINE_CONFIG.answer_notes[0];
    const env = fakeEnv();
    await writeRow(env.DB, await storedRow(note.target.question));
    const hit = (await servedHit(env.DB, { scope: note.target.scope, question: note.target.question, filters: {} })) as any;
    expect(hit.editorial_notes.map((n: { id: string }) => n.id)).toContain(note.id);
    expect(notesForAnswer(note.target.scope, note.target.question, false)).toEqual([]);   // cached_only
  });

  it("refuses rows that would store a visitor's question, and expires visitor rows", async () => {
    const env = fakeEnv();
    const bad = await storedRow("q", { curated: 0, question: "a visitor question", expires_at: "2099-01-01T00:00:00+00:00" });
    await expect(writeRow(env.DB, bad)).rejects.toThrow(/no question/);
    const old = await storedRow("old", { curated: 0, question: null, expires_at: "2026-01-01T00:00:00+00:00" });
    await writeRow(env.DB, old);
    expect(await readRow(env.DB, String(old.key))).toBeNull();
    expect(await purgeExpired(env.DB)).toBe(1);
    expect((env.DB as unknown as FakeD1).answers.size).toBe(0);
  });
});

describe("reading an /ask request", () => {
  it("reads GET permalinks and POST bodies and decides cacheability", async () => {
    const get = await readAsk(new Request("https://api.test/ask?q=tobacco&jurisdiction=ontario&scope=microlog"));
    expect(get?.input).toEqual({ scope: "microlog", question: "tobacco", filters: { jurisdiction: "ontario" } });
    expect(get?.cacheable).toBe(true);
    const nocache = await readAsk(new Request("https://api.test/ask?q=t&nocache=1"));
    expect(nocache?.cacheable).toBe(false);
    const post = await readAsk(new Request("https://api.test/ask", { method: "POST", body: JSON.stringify({ question: "q", provider: "stub" }) }));
    expect(post?.input.scope).toBe(ENGINE_CONFIG.default_scope);
    expect(post?.cacheable).toBe(false);
    expect(await readAsk(new Request("https://api.test/ask?q=t&scope=elsewhere"))).toBeNull();
  });
});

describe("guards", () => {
  it("requires a Turnstile token that siteverify accepts", async () => {
    const env = fakeEnv({ TURNSTILE_SECRET_KEY: "1x0000000000000000000000000000000AA" });
    const without = new Request("https://api.test/ask", { method: "POST" });
    expect((await checkTurnstile(without, env)).reason).toBe("turnstile_missing");
    const withToken = new Request("https://api.test/ask", { method: "POST", headers: { [TURNSTILE_HEADER]: "XXXX.DUMMY.TOKEN.XXXX" } });
    const pass = (async () => Response.json({ success: true })) as unknown as typeof fetch;
    const fail = (async () => Response.json({ success: false })) as unknown as typeof fetch;
    expect((await checkTurnstile(withToken, env, pass)).ok).toBe(true);
    expect((await checkTurnstile(withToken, env, fail)).reason).toBe("turnstile_failed");
    expect((await checkTurnstile(withToken, fakeEnv({ TURNSTILE_SECRET_KEY: undefined }), pass)).reason).toBe("turnstile_not_configured");
    expect((await checkTurnstile(without, fakeEnv({ TURNSTILE_REQUIRED: "false" }))).ok).toBe(true);
  });

  it("keys the rate limiter on a hash, never the address", async () => {
    const env = fakeEnv();
    const key = await clientKey(new Request("https://api.test/", { headers: { "cf-connecting-ip": "203.0.113.7" } }), env);
    expect(key).toMatch(/^[0-9a-f]{32}$/);
    expect(key).not.toContain("203");
  });

  it("counts the daily model budget", async () => {
    const env = fakeEnv({ DAILY_MODEL_CALLS: "2" });
    const day = new Date("2026-11-02T10:00:00Z");
    expect(await takeModelBudget(env.DB, env, day)).toBe(true);
    expect(await takeModelBudget(env.DB, env, day)).toBe(true);
    expect(await takeModelBudget(env.DB, env, day)).toBe(false);
    expect(await takeModelBudget(env.DB, env, new Date("2026-11-03T00:00:01Z"))).toBe(true);
  });

  it("allows CORS only for configured origins", () => {
    const env = fakeEnv({ ALLOWED_ORIGINS: "https://archiveargues.org, https://www.archiveargues.org" });
    const ok = corsHeaders(new Request("https://api.test/", { headers: { origin: "https://www.archiveargues.org" } }), env);
    expect(ok["access-control-allow-origin"]).toBe("https://www.archiveargues.org");
    expect(corsHeaders(new Request("https://api.test/", { headers: { origin: "https://evil.example" } }), env)).toEqual({});
  });
});

describe("keep-warm windows", () => {
  it("is off by default and follows UTC windows", () => {
    expect(keepWarmNow("", new Date())).toBe(false);
    const spec = "mon-fri 13:00-23:00; sat,sun 15:00-18:30";
    expect(parseWindows(spec)).toHaveLength(2);
    expect(keepWarmNow(spec, new Date("2026-11-02T14:00:00Z"))).toBe(true);    // Monday
    expect(keepWarmNow(spec, new Date("2026-11-02T23:00:00Z"))).toBe(false);
    expect(keepWarmNow(spec, new Date("2026-11-01T18:00:00Z"))).toBe(true);    // Sunday
    expect(keepWarmNow("someday 25:00-26:00", new Date())).toBe(false);         // malformed: stays cold
  });
});

describe("range reads for the container", () => {
  it("parses the one form provisioning sends", () => {
    expect(parseRange("bytes=0-99")).toEqual({ offset: 0, length: 100 });
    expect(parseRange(null)).toBeNull();
    expect(parseRange("bytes=10-")).toBe("invalid");
    expect(parseRange("bytes=9-3")).toBe("invalid");
  });
});

describe("stored answers carry an ETag", () => {
  it("answers 200 with a strong ETag, then 304 for the same ETag, and a new ETag when the body changes", async () => {
    const { storedAnswerResponse } = await import("../src/cache");
    const hit = { answer: { text: "Stored.", cached: { created_at: "2026-10-16T12:00:00+00:00" } }, evidence: [] };
    const first = await storedAnswerResponse(new Request("https://api.test/ask?q=x"), hit, {});
    const etag = first.headers.get("etag") ?? "";
    expect(first.status).toBe(200);
    expect(etag).toMatch(/^"[0-9a-f]{32}"$/);
    expect(first.headers.get("cache-control")).toBe("public, max-age=0, must-revalidate");
    expect(await first.json()).toEqual(hit);
    const again = await storedAnswerResponse(new Request("https://api.test/ask?q=x", { headers: { "if-none-match": etag } }), hit, {});
    expect(again.status).toBe(304);
    expect(await again.text()).toBe("");
    const changed = await storedAnswerResponse(new Request("https://api.test/ask?q=x", { headers: { "if-none-match": etag } }),
      { ...hit, editorial_notes: [{ id: "n" }] }, {});
    expect(changed.status).toBe(200);
    expect(changed.headers.get("etag")).not.toBe(etag);
  });
});
