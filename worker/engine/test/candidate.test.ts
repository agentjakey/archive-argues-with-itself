// The staging flag for an open writer: which cache context the Worker keys with, which model the
// container's AI proxy allows, and the chat completion shape the proxy hands back.
import { describe, expect, it } from "vitest";
import { readAsk } from "../src/ask";
import { ENGINE_CONFIG, asChatCompletion, candidateModel, scopeConfig } from "../src/config";

const scope = ENGINE_CONFIG.default_scope;
const configured = ENGINE_CONFIG.scopes[scope];
const names = Object.keys(configured.candidates ?? {});

describe("writer candidate flag", () => {
  it("leaves the configured writer in place when the flag is off or names nothing known", () => {
    expect(scopeConfig(scope)).toBe(configured);
    expect(scopeConfig(scope, "")).toBe(configured);
    expect(scopeConfig(scope, "no-such-candidate")).toBe(configured);
    expect(scopeConfig("no-such-scope", names[0])).toBeUndefined();
  });

  it("keys with the candidate's own context, keeping the reviewed v1 context", () => {
    expect(names.length).toBeGreaterThan(0);
    const c = scopeConfig(scope, names[0])!;
    expect(c.context).toBe(configured.candidates![names[0]].context);
    expect(c.context).not.toBe(configured.context);
    expect(c.curated_context).toBe(configured.curated_context);
    expect(c.provider).not.toBe("anthropic");
  });

  it("makes the candidate the configured model for a public ask", async () => {
    const request = new Request(`https://x/ask?scope=${scope}`, { method: "POST", body: JSON.stringify({ question: "q" }) });
    const off = await readAsk(request.clone(), { PUBLIC_MODELS: "", PUBLIC_NOCACHE: "" });
    const on = await readAsk(request.clone(), { PUBLIC_MODELS: "", PUBLIC_NOCACHE: "", WRITER_CANDIDATE: names[0] });
    expect(off?.cacheable).toBe(true);
    expect(on?.cacheable).toBe(true);
  });

  it("allows one model in the AI proxy, only with the binding present", () => {
    const fakeAi = {} as Ai;
    expect(candidateModel({ WRITER_CANDIDATE: "", AI: fakeAi })).toBeNull();
    expect(candidateModel({ WRITER_CANDIDATE: names[0] })).toBeNull();
    expect(candidateModel({ WRITER_CANDIDATE: "no-such-candidate", AI: fakeAi })).toBeNull();
    expect(candidateModel({ WRITER_CANDIDATE: names[0], AI: fakeAi })).toBe(configured.candidates![names[0]].model);
  });

  it("hands back an OpenAI-style completion whatever shape the binding returned", () => {
    const already = { choices: [{ message: { content: "{}" } }], usage: { prompt_tokens: 1 } };
    expect(asChatCompletion("m", already)).toBe(already);
    const old = asChatCompletion("m", { response: "text", usage: { prompt_tokens: 3, completion_tokens: 4 } }) as any;
    expect(old.choices[0].message.content).toBe("text");
    expect(old.usage.completion_tokens).toBe(4);
    const parsed = asChatCompletion("m", { response: { sentences: [] } }) as any;
    expect(JSON.parse(parsed.choices[0].message.content)).toEqual({ sentences: [] });
  });
});
