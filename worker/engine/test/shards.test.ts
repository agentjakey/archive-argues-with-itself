// Shards of the whole collection: a shard scope is served only where the deployment's SHARDS names
// it; every other scope is served everywhere. Shard names come from the generated config, never
// from this file.
import { describe, expect, it } from "vitest";
import { engineNames, readAsk } from "../src/ask";
import { ENGINE_CONFIG, SCOPES, scopeServed, servedScopes } from "../src/config";

const shards = SCOPES.filter((s) => ENGINE_CONFIG.scopes[s].shard);
const others = SCOPES.filter((s) => !ENGINE_CONFIG.scopes[s].shard);
const ask = (scope: string) =>
  new Request(`https://x/ask?scope=${encodeURIComponent(scope)}`, { method: "POST", body: JSON.stringify({ question: "q" }) });

describe("shard scopes", () => {
  it("serves every scope that is not a shard, with or without SHARDS", () => {
    for (const scope of others) {
      expect(scopeServed(scope, "")).toBe(true);
      expect(scopeServed(scope, undefined)).toBe(true);
    }
    expect(servedScopes("")).toEqual(others);
    expect(scopeServed("no-such-scope", "no-such-scope")).toBe(false);
  });

  it("serves a shard only where SHARDS names it, and its tier is in the config", () => {
    for (const scope of shards) {
      expect(scopeServed(scope, "")).toBe(false);
      expect(scopeServed(scope, ` ${scope} ,other`)).toBe(true);
      expect(["INDEXED", "AI-AUDITED", "HUMAN-AUDITED"]).toContain(ENGINE_CONFIG.scopes[scope].tier);
    }
    expect(servedScopes(shards.join(","))).toEqual(SCOPES);
  });

  it("refuses an ask for a shard the deployment does not serve, and wakes only served engines", async () => {
    const base = { PUBLIC_MODELS: "", PUBLIC_NOCACHE: "" };
    for (const scope of shards) {
      expect(await readAsk(ask(scope), { ...base, SHARDS: "" })).toBeNull();
      expect((await readAsk(ask(scope), { ...base, SHARDS: scope }))?.input.scope).toBe(scope);
      expect(engineNames({ ENGINE_LAYOUT: "split", SHARDS: "" })).not.toContain(scope);
      expect(engineNames({ ENGINE_LAYOUT: "split", SHARDS: scope })).toContain(scope);
    }
    expect(engineNames({ ENGINE_LAYOUT: "single", SHARDS: shards.join(",") })).toEqual(["engine"]);
  });
});
