import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// A site key, as in a release build, so every guarded request runs the person check.
vi.mock("../lib/config", () => ({
  API_BASE: "https://engine.example.test",
  STATIC_DATA: "",
  TURNSTILE_SITEKEY: "1x00000000000000000000AA",
  staticMode: () => false,
}));

import { AnswerCard, AI_LINE } from "../components/AnswerCard";
import { AskBar } from "../components/AskBar";
import { ErrorCard } from "../components/ErrorCard";
import { Footer } from "../components/Footer";
import { Accessibility } from "../components/pages/Accessibility";
import { Corrections } from "../components/pages/Corrections";
import { Privacy } from "../components/pages/Privacy";
import { Terms } from "../components/pages/Terms";
import { ask, CHECK_MESSAGES, RATE_LIMIT_MESSAGE, TurnstileError } from "../lib/api";
import { resetTurnstileForTests, SLOT_ID, turnstileResult } from "../lib/turnstile";
import { readState } from "../lib/urlstate";
import type { Answer } from "../types";
import { abstention, row } from "./fixtures";

type Options = Record<string, (...args: unknown[]) => unknown> & Record<string, unknown>;

/** A stand-in for window.turnstile that records how it was rendered and lets a test play the
 *  widget's part: hand out a token, fail, expire, or ask for an interactive check. */
function fakeTurnstile(onExecute: (options: Options) => void) {
  const rendered: { element: HTMLElement; options: Options }[] = [];
  const api = {
    render: vi.fn((element: HTMLElement, options: Options) => {
      rendered.push({ element, options });
      return `w${rendered.length}`;
    }),
    execute: vi.fn((id: string) => onExecute(rendered[Number(id.slice(1)) - 1].options)),
    reset: vi.fn(),
    remove: vi.fn(),
  };
  window.turnstile = api;
  return { api, rendered };
}

function slotElement(): HTMLElement {
  const slot = document.createElement("div");
  slot.id = SLOT_ID;
  document.body.appendChild(slot);
  return slot;
}

const okBody = {
  answer: { ...abstention(), cached: null },
  evidence: [],
  flagged: null,
  editorial_notes: [],
};

beforeEach(() => {
  resetTurnstileForTests();
  document.body.replaceChildren();
});

afterEach(() => {
  vi.unstubAllGlobals();
  delete window.turnstile;
});

describe("the person check beside Ask", () => {
  it("renders into the visible slot with the interaction-only appearance, so Invisible and Managed modes both work", async () => {
    const slot = slotElement();
    const { rendered } = fakeTurnstile((o) => (o.callback as (t: string) => void)("token-1"));
    const result = await turnstileResult();
    expect(result).toEqual({ token: "token-1", failure: null });
    expect(rendered).toHaveLength(1);
    expect(slot.contains(rendered[0].element)).toBe(true);
    expect(slot.closest("[aria-hidden]")).toBeNull();
    expect(rendered[0].options).toMatchObject({
      sitekey: "1x00000000000000000000AA",
      appearance: "interaction-only",
      execution: "execute",
    });
  });

  it("sends the token with the question and only then starts the request", async () => {
    slotElement();
    fakeTurnstile((o) => (o.callback as (t: string) => void)("token-2"));
    const fetchMock = vi.fn(async (_url: string, _init: RequestInit) => new Response(JSON.stringify(okBody), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    await ask({ question: "tobacco" });
    const init = fetchMock.mock.calls[0][1];
    expect((init.headers as Record<string, string>)["x-turnstile-token"]).toBe("token-2");
  });

  it("a failed check sends nothing and gives a plain message", async () => {
    slotElement();
    fakeTurnstile((o) => (o["error-callback"] as () => void)());
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    await expect(ask({ question: "tobacco" })).rejects.toThrow(CHECK_MESSAGES.failed);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("an expired token is reported as running out of time", async () => {
    slotElement();
    fakeTurnstile((o) => (o["expired-callback"] as () => void)());
    vi.stubGlobal("fetch", vi.fn());
    const err = await ask({ question: "tobacco" }).catch((e) => e);
    expect(err).toBeInstanceOf(TurnstileError);
    expect(err.detail).toBe(CHECK_MESSAGES.expired);
  });

  it("a token the engine refuses becomes the same plain message, never a raw code", async () => {
    slotElement();
    fakeTurnstile((o) => (o.callback as (t: string) => void)("spent"));
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ error: "turnstile_failed" }), { status: 403 })));
    const err = await ask({ question: "tobacco" }).catch((e) => e);
    expect(err).toBeInstanceOf(TurnstileError);
    expect(err.detail).toBe(CHECK_MESSAGES.refused);
    expect(err.detail).not.toMatch(/turnstile_/);
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ error: "rate_limited" }), { status: 429 })));
    const limited = await ask({ question: "tobacco" }).catch((e) => e);
    expect(limited.detail).toBe(RATE_LIMIT_MESSAGE);
  });

  it("an interactive check is announced beside Ask, and a new slot gets a new widget", async () => {
    const props = {
      question: "tobacco", filters: {}, busy: false, kiosk: false,
      onQuestion: vi.fn(), onFilters: vi.fn(), onAsk: vi.fn(),
    };
    const view = render(<AskBar {...props} />);
    let pending: Options | null = null;
    const { rendered } = fakeTurnstile((o) => {
      pending = o;
      (o["before-interactive-callback"] as () => void)();
    });
    const token = turnstileResult();
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });
    await vi.waitFor(() => expect(pending).not.toBeNull());
    expect(screen.getByRole("status")).toHaveTextContent(/confirm you are a person/);
    expect(document.getElementById(SLOT_ID)!.contains(rendered[0].element)).toBe(true);
    await act(async () => {
      (pending!["after-interactive-callback"] as () => void)();
      (pending!.callback as (t: string) => void)("token-3");
    });
    expect((await token).token).toBe("token-3");
    expect(screen.getByRole("status")).toHaveTextContent("");

    // The visitor moved to another page and back: the slot is a new element.
    view.unmount();
    render(<AskBar {...props} />);
    const second = fakeTurnstile((o) => (o.callback as (t: string) => void)("token-4"));
    expect((await turnstileResult()).token).toBe("token-4");
    expect(second.api.remove).toHaveBeenCalledWith("w1");
    expect(document.getElementById(SLOT_ID)!.contains(second.rendered[0].element)).toBe(true);
  });

  it("the error card offers a retry", () => {
    const onRetry = vi.fn();
    render(<ErrorCard detail={CHECK_MESSAGES.failed} onRetry={onRetry} />);
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(onRetry).toHaveBeenCalled();
  });
});

describe("the line beside every answer", () => {
  it("says who wrote it and to open the page", () => {
    const answer: Answer = {
      ...abstention(),
      abstained: false,
      sentences: [{ text: "Prices rose.", cited_ids: ["itemA#29:0"] }],
      verified_citations: [{ passage_id: "itemA#29:0" }] as Answer["verified_citations"],
    };
    render(<AnswerCard answer={answer} byId={new Map([["itemA#29:0", row({ cited: true })]])} onOpen={vi.fn()} />);
    expect(screen.getByText(AI_LINE)).toBeInTheDocument();
    expect(AI_LINE).toBe("Written by an AI model from the pages cited. It can be wrong; open the page to check.");
  });
});

describe("public pages", () => {
  it("the footer links every policy page, and each is a real view", () => {
    const onView = vi.fn();
    render(<Footer onView={onView} />);
    for (const [name, view] of [
      ["About", "about"], ["Privacy", "privacy"], ["Terms of use", "terms"],
      ["Accessibility", "accessibility"], ["Corrections and care", "corrections"],
    ] as const) {
      const link = screen.getByRole("link", { name });
      expect(link).toHaveAttribute("href", `?view=${view}`);
      expect(readState(`?view=${view}`).view).toBe(view);
      fireEvent.click(link);
      expect(onView).toHaveBeenLastCalledWith(view);
    }
  });

  it("each page carries a Last updated date", () => {
    for (const Page of [Privacy, Terms, Accessibility, Corrections]) {
      const { unmount } = render(<Page />);
      expect(screen.getByText(/Last updated/)).toBeInTheDocument();
      unmount();
    }
  });

  it("Privacy has the Turnstile sentence, the age line and the request not to type personal information", () => {
    render(<Privacy />);
    expect(
      screen.getByText((_, el) =>
        el?.tagName === "P" &&
        el.textContent ===
          "This site uses Cloudflare Turnstile to tell people from bots. Its use is governed by the Turnstile Privacy " +
            "Addendum (https://www.cloudflare.com/turnstile-privacy-policy/).",
      ),
    ).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Please don't type personal information into questions" })).toBeInTheDocument();
    expect(screen.getByText("The question feature is for people 18 and over.")).toBeInTheDocument();
    expect(screen.getByText(/Deleted after 90 days/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Cloudflare, Workers AI privacy/ })).toBeInTheDocument();
    expect(screen.getAllByText(/GLM-5\.3/).length).toBeGreaterThan(0);
  });

  it("no page claims compliance or full security", () => {
    for (const Page of [Privacy, Terms, Accessibility, Corrections]) {
      const { container, unmount } = render(<Page />);
      const text = container.textContent ?? "";
      expect(text).not.toMatch(/compliant with|fully secure|guarantee/i);
      unmount();
    }
  });
});
