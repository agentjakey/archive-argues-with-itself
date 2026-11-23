// Billing safeguards for Workers AI (src/aigateway.ts). Every test uses a fake AI binding that records
// its calls: no network request and no paid model call is ever made here.
import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { AiRefused, BUDGET_HEADER, dailyAiCalls, gatewayId, isBudgetError, refusalResponse, runGated, takeAiCall,
         type AiEnv } from "../src/aigateway";
import { FakeD1 } from "./fakes";

class FakeAi {
  calls: Array<{ model: string; inputs: unknown; options: any }> = [];
  constructor(private readonly behaviour: (n: number) => unknown = () => ({ response: "ok" })) {}
  async run(model: string, inputs: unknown, options?: unknown) {
    this.calls.push({ model, inputs, options });
    const out = this.behaviour(this.calls.length);
    if (out instanceof Error) throw out;
    return out;
  }
}

function env(over: Partial<AiEnv> & { ai?: FakeAi; db?: FakeD1 } = {}): AiEnv & { ai: FakeAi; db: FakeD1 } {
  const ai = over.ai ?? new FakeAi();
  const db = over.db ?? new FakeD1();
  return { AI: ai as unknown as Ai, DB: db as unknown as D1Database, AI_GATEWAY_ID: "archive-argues-staging",
           DAILY_AI_CALLS: "10", RELEASE_ID: "r1", ...over, ai, db } as any;
}
const NOW = new Date("2026-11-23T12:00:00Z");

describe("gateway routing", () => {
  it("sends every call through the configured gateway, with release metadata", async () => {
    const e = env();
    await runGated(e, "@cf/zai-org/glm-5.3", { messages: [] }, NOW);
    expect(e.ai.calls).toHaveLength(1);
    expect(e.ai.calls[0].options.gateway.id).toBe("archive-argues-staging");
    expect(e.ai.calls[0].options.gateway.metadata).toEqual({ release: "r1", source: "engine" });
  });

  it("fails closed with no gateway id: the binding is never called", async () => {
    for (const id of [undefined, "", "   ", "bad id!", "x".repeat(65)]) {
      const e = env({ AI_GATEWAY_ID: id });
      await expect(runGated(e, "m", {}, NOW)).rejects.toMatchObject({ status: 503, reason: "ai_gateway_not_configured" });
      expect(e.ai.calls).toHaveLength(0);
    }
  });

  it("accepts only plain gateway ids", () => {
    expect(gatewayId({ AI_GATEWAY_ID: " archive-argues-production " })).toBe("archive-argues-production");
    expect(gatewayId({ AI_GATEWAY_ID: "a/b" })).toBeNull();
  });

  it("refuses without an AI binding", async () => {
    const e = env(); (e as any).AI = undefined;
    await expect(runGated(e, "m", {}, NOW)).rejects.toMatchObject({ status: 503 });
  });
});

describe("per-day call ceiling", () => {
  it("takes the ceiling only from DAILY_AI_CALLS; unset or malformed means no calls at all", async () => {
    expect(dailyAiCalls({ DAILY_AI_CALLS: "330" })).toBe(330);
    for (const v of [undefined, "", "abc", "-5"]) expect(dailyAiCalls({ DAILY_AI_CALLS: v })).toBe(0);
    const e = env({ DAILY_AI_CALLS: undefined });
    await expect(runGated(e, "m", {}, NOW)).rejects.toMatchObject({ status: 429, reason: "daily_ai_calls_exhausted" });
    expect(e.ai.calls).toHaveLength(0);
  });

  it("allows exactly the ceiling: call n=limit succeeds, n=limit+1 is refused (no off-by-one)", async () => {
    const e = env({ DAILY_AI_CALLS: "1" });
    await runGated(e, "m", {}, NOW);
    await expect(runGated(e, "m", {}, NOW)).rejects.toMatchObject({ status: 429 });
    expect(e.ai.calls).toHaveLength(1);
  });

  it("counts by UTC day, not local time: 23:59:59Z and 00:00:00Z are different days", async () => {
    const e = env({ DAILY_AI_CALLS: "1" });
    await runGated(e, "m", {}, new Date("2026-11-23T23:59:59Z"));
    await runGated(e, "m", {}, new Date("2026-11-24T00:00:00Z"));
    expect([...e.db.aiCalls.keys()]).toEqual(["2026-11-23", "2026-11-24"]);
  });

  it("stops calling the model once the day's ceiling is reached, and resets the next UTC day", async () => {
    const e = env({ DAILY_AI_CALLS: "3" });
    for (let i = 0; i < 3; i++) await runGated(e, "m", {}, NOW);
    await expect(runGated(e, "m", {}, NOW)).rejects.toMatchObject({ status: 429, reason: "daily_ai_calls_exhausted" });
    await expect(runGated(e, "m", {}, NOW)).rejects.toBeInstanceOf(AiRefused);
    expect(e.ai.calls).toHaveLength(3);
    await runGated(e, "m", {}, new Date("2026-11-24T00:00:01Z"));
    expect(e.ai.calls).toHaveLength(4);
  });

  it("bounds a runaway caller: 1,000 attempts make at most the ceiling's calls", async () => {
    const e = env({ DAILY_AI_CALLS: "25" });
    const results = await Promise.allSettled(Array.from({ length: 1000 }, () => runGated(e, "m", {}, NOW)));
    expect(results.filter((r) => r.status === "fulfilled")).toHaveLength(25);
    expect(e.ai.calls).toHaveLength(25);
  });

  it("fails closed when the ceiling cannot be counted (no D1, D1 error, zero limit)", async () => {
    const db = new FakeD1(); db.failAiBudget = true;
    expect(await takeAiCall(db as unknown as D1Database, { DAILY_AI_CALLS: "10" }, NOW)).toBe(false);
    expect(await takeAiCall(undefined, { DAILY_AI_CALLS: "10" }, NOW)).toBe(false);
    expect(await takeAiCall(new FakeD1() as unknown as D1Database, { DAILY_AI_CALLS: "0" }, NOW)).toBe(false);
    const e = env({ db });
    await expect(runGated(e, "m", {}, NOW)).rejects.toMatchObject({ status: 429 });
    expect(e.ai.calls).toHaveLength(0);
  });
});

describe("budget-exceeded handling", () => {
  it("turns a gateway spend-limit or rate-limit refusal into a 429 with the budget header", async () => {
    for (const msg of ["AiError: 429 Too Many Requests", "Gateway spend limit reached", "rate limited"]) {
      const e = env({ ai: new FakeAi(() => new Error(msg)) });
      const err = await runGated(e, "m", {}, NOW).catch((x) => x);
      expect(err).toBeInstanceOf(AiRefused);
      const resp = refusalResponse(err);
      expect(resp.status).toBe(429);
      expect(resp.headers.get(BUDGET_HEADER)).toBe("exhausted");
      expect(e.ai.calls).toHaveLength(1);   // no retry after a budget refusal
    }
  });

  it("passes other model errors on unchanged (the proxy's 400/502 handling stays as it was)", async () => {
    const e = env({ ai: new FakeAi(() => new Error("invalid input schema")) });
    const err = await runGated(e, "m", {}, NOW).catch((x) => x);
    expect(err).not.toBeInstanceOf(AiRefused);
    expect(isBudgetError(err)).toBe(false);
  });
});

describe("no ungated path in the source", () => {
  const src = join(__dirname, "..", "src");
  it("only src/aigateway.ts calls the AI binding", () => {
    for (const f of readdirSync(src).filter((n) => n.endsWith(".ts"))) {
      if (f === "aigateway.ts") continue;
      expect(readFileSync(join(src, f), "utf8"), f).not.toMatch(/\.AI\.run\(|\bAI\.run\(/);
    }
  });

  it("every environment with an AI binding names its own gateway, not the audit gateway", () => {
    const text = readFileSync(join(__dirname, "..", "wrangler.jsonc"), "utf8").replace(/^\s*\/\/.*$/gm, "");
    const cfg = JSON.parse(text);
    const ids = new Set<string>();
    for (const [name, e] of Object.entries<any>(cfg.env)) {
      if (!e.ai) continue;
      const id = e.vars?.AI_GATEWAY_ID;
      expect(gatewayId({ AI_GATEWAY_ID: id }), `${name} AI_GATEWAY_ID`).not.toBeNull();
      expect(id).not.toBe("archive-argues-audit");
      expect(Number(e.vars?.DAILY_AI_CALLS), `${name} DAILY_AI_CALLS`).toBeGreaterThan(0);
      // the call ceiling may not widen spending past the question budget (+10% for schema fallbacks)
      expect(Number(e.vars.DAILY_AI_CALLS), `${name} DAILY_AI_CALLS vs DAILY_MODEL_CALLS`)
        .toBeLessThanOrEqual(Math.ceil(1.1 * Number(e.vars.DAILY_MODEL_CALLS)));
      ids.add(id);
    }
    expect(ids.size).toBe(Object.values<any>(cfg.env).filter((e) => e.ai).length);
  });
});
