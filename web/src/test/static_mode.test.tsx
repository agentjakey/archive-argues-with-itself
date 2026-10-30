import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import vectors from "../../../config/cache_key_vectors.json";
import { WakingCard, stageLine } from "../components/WakingCard";
import { canonicalFilters, normalizeQuestion, sameFilters } from "../lib/curated";
import { recordedLine } from "../lib/recorded";
import { DOWN_AFTER_S, EngineDown, SLOW_AFTER_S, waitForEngine, type WakeProgress } from "../lib/waking";
import type { Answer, EngineStatus } from "../types";

describe("recognizing a curated question, as the engine does", () => {
  for (const v of vectors.vectors) {
    it(v.name, () => {
      expect(normalizeQuestion(v.question)).toBe(v.normalized_question);
      expect(canonicalFilters(v.filters as Record<string, unknown> | null)).toEqual(v.canonical_filters);
    });
  }

  it("compares canonical filters exactly", () => {
    expect(sameFilters({ jurisdiction: "alberta" }, { jurisdiction: "alberta" })).toBe(true);
    expect(sameFilters({ jurisdiction: "alberta" }, {})).toBe(false);
    expect(sameFilters(null, {})).toBe(false);
  });
});

function fakeClock() {
  let ms = 0;
  return {
    now: () => ms,
    sleep: async (seconds: number) => {
      ms += seconds * 1000;
    },
  };
}

describe("waiting for a waking engine", () => {
  it("reports progress and resolves once the engine is ready", async () => {
    const clock = fakeClock();
    const replies: EngineStatus[] = [
      { status: "waking", stage: { stage: "downloading", bytes_total: 100, bytes_downloaded: 10 } },
      { status: "waking", stage: { stage: "loading" } },
      { status: "ready" },
    ];
    const seen: WakeProgress[] = [];
    await waitForEngine(0, { status: async () => replies.shift()!, ...clock }, (p) => seen.push(p), new AbortController().signal);
    expect(seen.map((p) => p.stage?.stage)).toEqual(["downloading", "loading"]);
    expect(seen.every((p) => p.phase === "waking")).toBe(true);
  });

  it("says slow after a minute and down after a failed start", async () => {
    const clock = fakeClock();
    const seen: WakeProgress[] = [];
    let polls = 0;
    const status = async (): Promise<EngineStatus> => {
      polls += 1;
      if (clock.now() / 1000 > SLOW_AFTER_S + 10) return { status: "failed", error: "sha256 mismatch" };
      return { status: "waking", stage: { stage: "downloading" } };
    };
    await expect(waitForEngine(0, { status, ...clock }, (p) => seen.push(p), new AbortController().signal)).rejects.toThrow(EngineDown);
    expect(seen.some((p) => p.phase === "slow")).toBe(true);
    expect(polls).toBeGreaterThan(5);
  });

  it("gives up when the engine stays unreachable or takes too long", async () => {
    const unreachable = async (): Promise<EngineStatus> => {
      throw new Error("offline");
    };
    await expect(waitForEngine(0, { status: unreachable, ...fakeClock() }, () => {}, new AbortController().signal)).rejects.toThrow(
      /could not be reached/,
    );
    const forever = async (): Promise<EngineStatus> => ({ status: "waking", stage: null });
    const clock = fakeClock();
    await expect(waitForEngine(0, { status: forever, ...clock }, () => {}, new AbortController().signal)).rejects.toThrow(/in time/);
    expect(clock.now() / 1000).toBeGreaterThanOrEqual(DOWN_AFTER_S);
  });

  it("stops when the question is replaced", async () => {
    const ctrl = new AbortController();
    ctrl.abort();
    await expect(
      waitForEngine(0, { status: async () => ({ status: "waking" }), ...fakeClock() }, () => {}, ctrl.signal),
    ).rejects.toThrow(/aborted/);
  });
});

describe("the waking screen", () => {
  it("keeps the question, names the stage and shows the bytes fetched", () => {
    render(
      <WakingCard
        wake={{ phase: "waking", elapsed: 12, stage: { stage: "downloading", bytes_total: 7_700_000_000, bytes_downloaded: 1_500_000_000 } }}
        question="How did tobacco control policy change in Ontario?"
        onRetry={() => {}}
      />,
    );
    expect(screen.getByRole("status")).toHaveTextContent("Waking the archive engine");
    expect(screen.getByText(/How did tobacco control policy change in Ontario\?/)).toBeInTheDocument();
    expect(screen.getByText(/1\.5 of 7\.7 GB/)).toBeInTheDocument();
    expect(screen.getByLabelText("Archive files fetched so far")).toBeInTheDocument();
  });

  it("points to the stories and offers a retry when the engine is down", () => {
    const retry = vi.fn();
    render(<WakingCard wake={{ phase: "down", elapsed: 300, stage: null }} question="q" onRetry={retry} />);
    expect(screen.getByRole("status")).toHaveTextContent("not answering right now");
    expect(screen.getByText(/recorded answers, with every page cited/)).toBeInTheDocument();
    screen.getByRole("button", { name: "Try again" }).click();
    expect(retry).toHaveBeenCalled();
  });

  it("describes every stage in plain words", () => {
    expect(stageLine(null)).toBe("Starting up.");
    expect(stageLine({ stage: "checking" })).toMatch(/Checking/);
    expect(stageLine({ stage: "loading" })).toMatch(/indexes/);
  });
});

describe("a recorded answer says what it is", () => {
  it("names the date, model and prompt version", () => {
    const answer = {
      cached: { created_at: "2026-10-16T12:00:00+00:00" },
      generation: { model: "claude-haiku-4-5-20251001", prompt_sha256: "e8d1accdaf13d07d" },
    } as unknown as Answer;
    expect(recordedLine(answer)).toBe(
      "Recorded answer, generated 2026-10-16 by claude-haiku-4-5-20251001, prompt version e8d1accd. Shown as it was generated.",
    );
    expect(recordedLine({ cached: null } as unknown as Answer)).toBeNull();
  });
});

describe("static mode routing", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
    vi.resetModules();
  });

  it("serves a recorded answer from the shards and sends other questions to the engine Worker", async () => {
    vi.stubEnv("VITE_STATIC_DATA", "/data");
    vi.stubEnv("VITE_API_BASE", "https://api.example.test");
    const index = {
      format_version: 1, scope: "pilot",
      answers: [{ label: "seed:q001", question: "Tobacco?", normalized_question: "Tobacco?", filters: {}, file: "answers/seed-q001.json" }],
    };
    const recorded = { answer: { text: "Recorded." }, evidence: [] };
    const calls: string[] = [];
    vi.stubGlobal("fetch", async (url: string) => {
      calls.push(url);
      if (url === "/data/scopes.json") return Response.json({ default: "pilot", scopes: [] });
      if (url === "/data/pilot/answers/index.json") return Response.json(index);
      if (url === "/data/pilot/answers/seed-q001.json") return Response.json(recorded);
      if (url.startsWith("https://api.example.test/ask")) {
        return Response.json({ status: "waking", stage: { stage: "downloading" } }, { status: 503 });
      }
      return new Response("not found", { status: 404 });
    });
    const api = await import("../lib/api");
    expect(await api.ask({ question: "  Tobacco? " })).toEqual(recorded);
    await expect(api.ask({ question: "Something else" })).rejects.toBeInstanceOf(api.EngineWaking);
    expect(calls.filter((u) => u.startsWith("https://api.example.test/ask"))).toHaveLength(1);
  });
});
