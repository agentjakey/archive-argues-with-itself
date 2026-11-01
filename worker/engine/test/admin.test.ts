// The operator wake: absent without a token, rate limited before the token is compared, and never
// linked from the site.
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { checkAdmin, sameSecret } from "../src/admin";
import { fakeEnv } from "./fakes";

const TOKEN = "k3J9xQ2mV8rT5wZ1nB7cL4hF6dS0aP2u";

function limiter(allowance: number) {
  const seen: string[] = [];
  return {
    seen,
    async limit({ key }: { key: string }) {
      seen.push(key);
      allowance -= 1;
      return { success: allowance >= 0 };
    },
  } as unknown as RateLimit & { seen: string[] };
}

function post(auth?: string): Request {
  const headers: Record<string, string> = {};
  if (auth !== undefined) headers.authorization = auth;
  return new Request("https://api.test/admin/wake?scope=pilot", { method: "POST", headers });
}

describe("the operator wake", () => {
  it("does not exist when no token is configured, and never touches the limiter then", async () => {
    const rl = limiter(5);
    const result = await checkAdmin(post(`Bearer ${TOKEN}`), fakeEnv(), rl);
    expect(result).toEqual({ ok: false, status: 404, reason: "not_found" });
    expect(rl.seen).toEqual([]);
  });

  it("accepts the configured bearer token and refuses anything else", async () => {
    const env = fakeEnv({ ADMIN_WAKE_TOKEN: TOKEN });
    expect((await checkAdmin(post(`Bearer ${TOKEN}`), env, limiter(5))).ok).toBe(true);
    for (const auth of [undefined, "", TOKEN, `Bearer ${TOKEN}x`, `Bearer ${TOKEN.slice(0, -1)}`, "Bearer short", `Basic ${TOKEN}`]) {
      const result = await checkAdmin(post(auth), env, limiter(5));
      expect(result.ok).toBe(false);
      expect(result.status).toBe(401);
    }
  });

  it("is rate limited on one shared key before the token is compared", async () => {
    const env = fakeEnv({ ADMIN_WAKE_TOKEN: TOKEN });
    const rl = limiter(1);
    expect((await checkAdmin(post("Bearer wrong-token-wrong-token"), env, rl)).status).toBe(401);
    expect(await checkAdmin(post(`Bearer ${TOKEN}`), env, rl)).toEqual({ ok: false, status: 429, reason: "rate_limited" });
    expect(rl.seen).toEqual(["admin-wake", "admin-wake"]);
  });

  it("compares secrets by hash", async () => {
    expect(await sameSecret(TOKEN, TOKEN)).toBe(true);
    expect(await sameSecret(TOKEN, TOKEN + "a")).toBe(false);
  });

  it("is never named by the site", () => {
    const roots = [join(__dirname, "..", "..", "..", "web", "src"), join(__dirname, "..", "..", "..", "site")];
    const hits: string[] = [];
    const walk = (dir: string) => {
      for (const name of readdirSync(dir)) {
        const path = join(dir, name);
        if (statSync(path).isDirectory()) walk(path);
        else if (/\.(ts|tsx|js|html|json|css|md)$/.test(name) && readFileSync(path, "utf8").includes("/admin/")) hits.push(path);
      }
    };
    for (const root of roots) {
      try {
        walk(root);
      } catch {
        // a root that does not exist in this checkout has nothing to name
      }
    }
    expect(hits).toEqual([]);
  });
});
