import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AbstentionCard } from "./components/AbstentionCard";
import { AnswerCard } from "./components/AnswerCard";
import { LimitedModeCard } from "./components/LimitedModeCard";
import { AskBar } from "./components/AskBar";
import { StoryGallery } from "./components/Stories";
import { CompareView } from "./components/CompareView";
import { CorpusStrip } from "./components/CorpusStrip";
import { CoveragePanel } from "./components/CoveragePanel";
import { ContextualNote } from "./components/ContextualNote";
import { EntryAdvisory } from "./components/EntryAdvisory";
import { ErrorCard } from "./components/ErrorCard";
import { EvidenceTrail } from "./components/EvidenceTrail";
import { Interstitial } from "./components/Interstitial";
import { ExampleChips } from "./components/ExampleChips";
import { Footer } from "./components/Footer";
import { Header } from "./components/Header";
import { PageDrawer } from "./components/PageDrawer";
import { AnswerSkeleton, SkeletonBody } from "./components/AnswerSkeleton";
import { useAsk } from "./hooks/useAsk";
import { useCoverage } from "./hooks/useCoverage";
import { useExamples } from "./hooks/useExamples";
import { useKiosk, useOffline } from "./hooks/useKiosk";
import { About } from "./components/pages/About";
import { Gaps } from "./components/pages/Gaps";
import { HowItWorks } from "./components/pages/HowItWorks";
import { SourcesPage } from "./components/pages/Sources";
import { ExplorePage } from "./components/pages/Explore";
import { TimelinePage } from "./components/pages/Timeline";
import { SourceLine } from "./components/SourceLine";
import { CoverageMap } from "./components/CoverageMap";
import { useAttractLoop } from "./hooks/useAttractLoop";
import { useScopes } from "./hooks/useScopes";
import { useScopeExamples } from "./hooks/useScopeExamples";
import { useStories } from "./hooks/useStories";
import { ask as apiAsk, flag as apiFlag } from "./lib/api";
import { applyState, documentTitle, readState, type View } from "./lib/urlstate";
import { mergeFlagged, needsInterstitial } from "./lib/sensitivity";
import { PROVINCE_SLUGS } from "./lib/coverage";
import { periodOfRow, pickDecadeRows } from "./lib/timeline";
import { plural } from "./lib/format";
import type { EvidenceRow, Example, Filters, Flagged, Period, Story } from "./types";

export default function App() {
  const kiosk = useKiosk();
  const offline = useOffline();   // ?offline=1: no ask box, cached questions and stories only
  const chips = useExamples();
  const { status, elapsed, response, error, run } = useAsk();

  const initial = useRef(readState(window.location.search));
  const [question, setQuestion] = useState(initial.current.q);
  const [filters, setFilters] = useState<Filters>(initial.current.filters);
  const [asked, setAsked] = useState(initial.current.q);
  const [askedFilters, setAskedFilters] = useState<Filters>(initial.current.filters);
  const [pins, setPins] = useState<string[]>(initial.current.pins);
  const [drawer, setDrawer] = useState<EvidenceRow | null>(null);
  const [chipsCollapsed, setChipsCollapsed] = useState(false);
  const [view, setView] = useState<View | null>(initial.current.view ?? null);
  const [storyRows, setStoryRows] = useState<[EvidenceRow, EvidenceRow] | null>(null);
  const [storyCaption, setStoryCaption] = useState<string | null>(null);
  const [storyFlagged, setStoryFlagged] = useState<Flagged | null>(null);   // over the story's pins
  const [pinFlagged, setPinFlagged] = useState<Flagged | null>(null);       // over a free user-pinned pair
  const [flaggedAck, setFlaggedAck] = useState(false);   // interstitial acknowledged for the current result
  // Thematic-timeline two-decade comparison. It reuses the EXISTING CompareView: the question is
  // asked once (unfiltered, so the pool spans decades), then one pool passage per chosen decade is
  // picked client-side (no extra retrieval, no extra cache write). pending holds the two periods
  // until that response arrives.
  const [pendingDecadeCompare, setPendingDecadeCompare] = useState<{ a: Period; b: Period } | null>(null);
  const [decadeCompare, setDecadeCompare] = useState<{ a: EvidenceRow; b: EvidenceRow; terms: string[] } | null>(null);
  const [decadeCompareNote, setDecadeCompareNote] = useState<string | null>(null);
  // True while a chosen decade absent from the unfiltered pool is being filled on demand with a
  // period-filtered retrieval, so the compare view shows progress instead of appearing to do nothing.
  const [decadeCompareLoading, setDecadeCompareLoading] = useState(false);
  // When a period fill is interrupted or times out (not a genuine empty result), hold the two periods
  // so the honest "did not finish in time" note can offer a retry, and run the same elapsed counter
  // the main skeleton uses so the two-phase wait reads as one process (A2.3, A3).
  const [decadeRetry, setDecadeRetry] = useState<{ a: Period; b: Period } | null>(null);
  const [decadeElapsed, setDecadeElapsed] = useState(0);
  const { stories, loading: storiesLoading } = useStories();
  const scopesInfo = useScopes();
  const activeScopeInfo =
    scopesInfo?.scopes.find((s) => s.name === (initial.current.scope ?? scopesInfo.default)) ?? null;
  const scopeExamples = useScopeExamples((scopesInfo?.scopes ?? []).map((s) => s.name));
  const coverage = useCoverage(asked, askedFilters);

  const goView = useCallback(
    (next: View | null) => {
      setView(next);
      applyState({ q: asked, filters: askedFilters, pins, kiosk, offline, view: next ?? undefined }, "push");
      window.scrollTo({ top: 0 });
    },
    [asked, askedFilters, pins, kiosk, offline],
  );

  // The nav "Ask" returns to the landing AND focuses the ask input, so asking is one click from any
  // page. Coming from another page, the focus-on-nav effect below does it (flagged here); when
  // already on the landing the view does not change, so the effect will not fire and we focus now.
  const focusAskNext = useRef(false);
  const goAsk = useCallback(() => {
    const already = view === null;
    focusAskNext.current = true;
    goView(null);
    if (already) {
      focusAskNext.current = false;
      const input = document.getElementById("question") as HTMLInputElement | null;
      input?.scrollIntoView({ behavior: "smooth", block: "center" });
      input?.focus({ preventScroll: true });
    }
  }, [view, goView]);

  // Back/forward buttons move between the ask view and the reading pages.
  useEffect(() => {
    const onPop = () => setView(readState(window.location.search).view ?? null);
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);

  // Per-view browser tab title, driven off the same view state the nav uses.
  useEffect(() => {
    document.title = documentTitle(view);
  }, [view]);

  // Announce a page change by moving focus to the new view's heading (reading pages have
  // #page-heading) or its main landmark (home). Skips the first render, so it never steals focus on
  // load, only on navigation.
  const navigated = useRef(false);
  useEffect(() => {
    if (!navigated.current) {
      navigated.current = true;
      return;
    }
    if (focusAskNext.current) {
      focusAskNext.current = false;
      const input = document.getElementById("question") as HTMLInputElement | null;
      if (input) {
        input.scrollIntoView({ behavior: "smooth", block: "center" });
        input.focus({ preventScroll: true });
        return;
      }
    }
    const target = document.getElementById("page-heading") ?? document.getElementById("main-content");
    target?.focus({ preventScroll: true });
  }, [view]);

  // Restore from the URL on load and run the ask.
  useEffect(() => {
    if (initial.current.q) void run({ question: initial.current.q, filters: initial.current.filters });
  }, [run]);

  // Restore a story comparison from a permalink once the stories have loaded.
  const storyRestored = useRef(false);
  useEffect(() => {
    if (storyRestored.current || !initial.current.story || stories.length === 0) return;
    const s = stories.find((x) => x.id === initial.current.story);
    if (s) {
      setStoryRows(s.pins);
      setStoryCaption(s.caption);
      setStoryFlagged(s.flagged ?? null);
      storyRestored.current = true;
    }
  }, [stories]);

  // A free user-pinned pair (not a story) is flagged over exactly those two passages, so a
  // pinned comparison carries the same note as every other flagged surface. Offline-safe:
  // the call hits the local API; on any failure we degrade to no note and never block.
  useEffect(() => {
    if (storyRows || pins.length !== 2) {
      setPinFlagged(null);
      return;
    }
    let cancelled = false;
    apiFlag(pins)
      .then((r) => {
        if (!cancelled) setPinFlagged(r.flagged ?? null);
      })
      .catch(() => {
        if (!cancelled) setPinFlagged(null);
      });
    return () => {
      cancelled = true;
    };
  }, [pins, storyRows]);

  const byId = useMemo(() => {
    const m = new Map<string, EvidenceRow>();
    response?.evidence.forEach((r) => m.set(r.passage_id, r));
    return m;
  }, [response]);

  const matched = useMemo(() => {
    if (!coverage) return null;
    const m: Record<string, number> = {};
    coverage.by_decade.forEach((d) => (m[d.decade] = d.matched));
    return m;
  }, [coverage]);

  const ask = useCallback(
    (q: string, f: Filters) => {
      setAsked(q);
      setAskedFilters(f);
      setPins([]);
      setStoryRows(null);
      setStoryCaption(null);
      setStoryFlagged(null);
      setPinFlagged(null);
      setDecadeCompare(null);       // a fresh ask clears any decade comparison...
      setDecadeCompareNote(null);
      setDecadeCompareLoading(false);
      setPendingDecadeCompare(null);   // ...but onCompareDecades sets pendingDecadeCompare after this
      setFlaggedAck(false);   // each new result must re-acknowledge its interstitial
      setDrawer(null);
      setChipsCollapsed(true);
      applyState({ q, filters: f, pins: [], kiosk, offline }, "push");
      void run({ question: q, filters: f });
    },
    [run, kiosk, offline],
  );

  const onAsk = useCallback(() => ask(question.trim(), filters), [ask, question, filters]);

  // A story asks its question and shows its two pinned pages side by side, whatever
  // the retrieval pool holds.
  const openStory = useCallback(
    (s: Story) => {
      setView(null);
      setQuestion(s.question);
      setFilters(s.filters ?? {});
      ask(s.question, s.filters ?? {});
      setStoryRows(s.pins);
      setStoryCaption(s.caption);
      setStoryFlagged(s.flagged ?? null);
      // carry the story in the URL so its permalink reproduces the comparison
      applyState({ q: s.question, filters: s.filters ?? {}, pins: [], kiosk, offline, story: s.id }, "replace");
      window.scrollTo({ top: 0 });
    },
    [ask, kiosk, offline],
  );

  // ?idle=<seconds> tunes the attract-loop dwell for the venue; default 60 s. Captured once
  // from the launch URL so it is the single source of truth for both the dwell and the
  // return-home URL: SPA navigation drops idle from window.location.search, so goHome cannot
  // re-read it live.
  const idleParam = useRef(new URLSearchParams(window.location.search).get("idle"));
  // Kiosk attract loop: idle -> cycle stories; any touch -> back to the home screen. goHome
  // reloads to the bare kiosk URL (clearing any typed-but-unsent question), carrying the kiosk
  // launch params so the dwell stays at the launched ?idle= value across every return-home.
  const goHome = useCallback(() => {
    // Carry the active scope so an attract/idle reset returns to the same corpus's home, not the
    // pilot default: scope survives the idle reset and the attract timeout.
    const scope = initial.current.scope;
    const def = scopesInfo?.default ?? "";
    const flags = [
      scope && scope !== def ? `scope=${encodeURIComponent(scope)}` : "",
      kiosk ? "kiosk=1" : "",
      offline ? "offline=1" : "",
      idleParam.current ? `idle=${encodeURIComponent(idleParam.current)}` : "",
    ].filter(Boolean).join("&");
    const target = `${window.location.pathname}${flags ? `?${flags}` : ""}`;
    // Idempotent: if already on the clean home for this scope, do not reload, so a no-story scope
    // (microlog) resets to home once on idle, then rests without re-blinking every idle interval.
    if (window.location.pathname + window.location.search === target) return;
    window.location.assign(target);
  }, [kiosk, offline, scopesInfo]);
  const idleMs = useMemo(() => {
    const v = Number(idleParam.current);
    return Number.isFinite(v) && v > 0 ? v * 1000 : undefined;
  }, []);
  useAttractLoop({ enabled: kiosk, stories, onShow: openStory, onHome: goHome, idleMs });

  // Switch corpora with a full reload into a clean copy of the CURRENT page for the chosen scope:
  // the page (view) is kept so the switch stays where you are, but no q/filters/pins/story carry
  // over, so no result from the other corpus can linger. Only the venue launch flags
  // (kiosk/offline/idle) are preserved. The pilot is the default and carries no ?scope.
  const switchScope = useCallback(
    (name: string) => {
      const def = scopesInfo?.default ?? "";
      const params = new URLSearchParams();
      if (name && name !== def) params.set("scope", name);
      if (view) params.set("view", view);   // stay on the current page after the switch, not bounce home
      if (kiosk) params.set("kiosk", "1");
      if (offline) params.set("offline", "1");
      if (idleParam.current) params.set("idle", idleParam.current);
      const qs = params.toString();
      window.location.assign(`${window.location.pathname}${qs ? `?${qs}` : ""}`);
    },
    [scopesInfo, kiosk, offline, view],
  );

  // Enter a corpus on a specific question from the explorer: reload into that scope with the
  // question (and its filters) in the URL, so the app runs it there and lands on the cited answer
  // (a warmed seed question returns instantly from cache). The full reload keeps the same clean
  // cross-scope reset the switcher guarantees.
  const enterScopeWithQuestion = useCallback(
    (name: string, text: string, f: Filters) => {
      const def = scopesInfo?.default ?? "";
      const params = new URLSearchParams();
      if (name && name !== def) params.set("scope", name);
      if (text) params.set("q", text);
      for (const k of ["period", "jurisdiction", "doc_type"] as const) {
        const v = (f as Record<string, string | undefined>)[k];
        if (v) params.set(k, v);
      }
      if (kiosk) params.set("kiosk", "1");
      if (offline) params.set("offline", "1");
      if (idleParam.current) params.set("idle", idleParam.current);
      const qs = params.toString();
      window.location.assign(`${window.location.pathname}${qs ? `?${qs}` : ""}`);
    },
    [scopesInfo, kiosk, offline],
  );

  const pick = useCallback(
    (e: Example) => {
      setQuestion(e.text);
      setFilters(e.filters ?? {});
      ask(e.text, e.filters ?? {});
    },
    [ask],
  );

  // Clicking a resolved province on the coverage map explores that province's cited record through
  // the EXISTING jurisdiction filter (no change to the frozen retriever). If a question is already
  // asked, re-run it scoped to the province; otherwise land on the ask view with the filter set so
  // the next question is province-scoped. The floor caveat is shown in the filtered view below.
  const exploreProvince = useCallback(
    (slug: string) => {
      const f: Filters = { ...askedFilters, jurisdiction: slug as Filters["jurisdiction"] };
      setView(null);
      setFilters(f);
      if (asked) {
        ask(asked, f);
      } else {
        setAskedFilters(f);
        applyState({ q: "", filters: f, pins: [], kiosk, offline }, "push");
      }
      window.scrollTo({ top: 0 });
    },
    [asked, askedFilters, kiosk, offline, ask],
  );

  // Drill from the timeline into one decade: run the question scoped to that period through the
  // EXISTING period filter (the frozen retriever already applies it), so the answer and evidence
  // trail are that decade's passages. Same shape as exploreProvince, one filter instead of the
  // other. With no question yet, land on the ask view with the period set so the next question is
  // decade-scoped.
  const onDrillDecade = useCallback(
    (period: Period, q: string) => {
      const text = q.trim();
      const f: Filters = { period };
      setView(null);
      setQuestion(text);
      setFilters(f);
      if (text) {
        ask(text, f);
      } else {
        setAskedFilters(f);
        applyState({ q: "", filters: f, pins: [], kiosk, offline }, "push");
      }
      window.scrollTo({ top: 0 });
    },
    [ask, kiosk, offline],
  );

  // Compare two decades in the EXISTING compare view. Ask the question once, unfiltered, so the
  // retrieval pool spans decades; pendingDecadeCompare then picks one pool passage per chosen
  // period once the response arrives (see the effect below). No period-filtered retrieval and no
  // extra cache write beyond the single ask; it works offline, where the degraded response still
  // carries the full pool.
  const onCompareDecades = useCallback(
    (q: string, a: Period, b: Period) => {
      const text = q.trim();
      if (!text || a === b) return;
      setView(null);
      setQuestion(text);
      setFilters({});
      ask(text, {});
      setPendingDecadeCompare({ a, b });
      setDecadeCompareLoading(true);   // enter compare mode at once; the effect fills and resolves it
      window.scrollTo({ top: 0 });
    },
    [ask],
  );

  // Resolve a pending two-decade comparison once its answer's pool is in. Pick the top-ranked pool
  // passage in each period (period_of matches the histogram's buckets). For a period the unfiltered
  // pool did not surface, fill that column on demand with one period-filtered retrieval: the EXISTING
  // /ask path, no model call (provider "stub"), so N1 holds (no new external call, reuses retrieval).
  // Only a period with no passage even then is reported as empty, so the compare view never
  // dead-ends: it shows a real side-by-side comparison or a clear inline reason.
  useEffect(() => {
    if (!pendingDecadeCompare || !response) return;
    const { a, b } = pendingDecadeCompare;
    // NOTE: do NOT clear pendingDecadeCompare here. Clearing it is a dependency change that re-runs
    // this effect, whose cleanup then flips `cancelled` on the in-flight run, so settle() below would
    // be skipped and the "Looking for a passage" state would hang forever when a fill is needed. The
    // pending compare is consumed inside settle() instead, once the work is actually done.
    const question = asked;
    const terms = response.answer.coverage.salient_terms ?? [];

    const settle = (rowA: EvidenceRow | null, rowB: EvidenceRow | null, timedOut: Set<Period>) => {
      setPendingDecadeCompare(null);   // consume only now that the comparison has resolved
      setDecadeCompareLoading(false);
      if (rowA && rowB) {
        setDecadeCompare({ a: rowA, b: rowB, terms });
        setDecadeCompareNote(null);
        setDecadeRetry(null);
        return;
      }
      setDecadeCompare(null);
      const missing = [!rowA ? a : null, !rowB ? b : null].filter(Boolean) as Period[];
      const slow = missing.filter((p) => timedOut.has(p));
      if (slow.length > 0) {
        // A fill that did not finish in time is NOT an absence in the record. Say so plainly and
        // offer a retry; never present a timeout as "the record has no passage here" (A2.3).
        setDecadeRetry({ a, b });
        setDecadeCompareNote(
          `The search for ${slow.join(" and ")} did not finish in time, so this comparison is not ` +
            `ready yet. Nothing is missing from the record; the search just ran long. Try it again.`,
        );
      } else {
        setDecadeRetry(null);
        setDecadeCompareNote(
          `The record has no passage in ${missing.join(" and ")} for this question, even when the ` +
            `search is narrowed to that period, so there is nothing to compare there. Try another ` +
            `decade or a different question.`,
        );
      }
    };

    const picked = pickDecadeRows(response.evidence, a, b);
    if (picked.missing.length === 0) {
      settle(picked.rowA, picked.rowB, new Set());
      return;
    }

    setDecadeCompareLoading(true);
    let cancelled = false;
    Promise.all(
      picked.missing.map((p) =>
        apiAsk({ question, filters: { period: p }, provider: "stub" })
          // A degraded stub response (budget or an interrupted scan) did not complete normally, so
          // its missing row is a timeout, not a real absence; a thrown error (client abort / network)
          // is likewise "did not finish," never an absence.
          .then((r) => ({
            p,
            row: r.evidence.find((e) => periodOfRow(e) === p) ?? null,
            timedOut: Boolean(r.degraded),
          }))
          .catch(() => ({ p, row: null as EvidenceRow | null, timedOut: true })),
      ),
    ).then((fills) => {
      if (cancelled) return;
      let rowA = picked.rowA;
      let rowB = picked.rowB;
      const timedOut = new Set<Period>();
      for (const { p, row, timedOut: to } of fills) {
        if (row && p === a) rowA = row;
        if (row && p === b) rowB = row;
        if (!row && to) timedOut.add(p);
      }
      settle(rowA, rowB, timedOut);
    });
    return () => {
      cancelled = true;
    };
  }, [response, pendingDecadeCompare, asked]);

  const clearDecadeCompare = useCallback(() => {
    setDecadeCompare(null);
    setDecadeCompareNote(null);
    setDecadeCompareLoading(false);
    setPendingDecadeCompare(null);
    setDecadeRetry(null);
  }, []);

  // Elapsed counter for the two-decade fill, so its "looking for a passage" state carries the same
  // honest progress signal as the main skeleton. Resets to 0 when the fill starts, ticks each second.
  useEffect(() => {
    if (!decadeCompareLoading) return;
    setDecadeElapsed(0);
    const t0 = Date.now();
    const id = window.setInterval(() => setDecadeElapsed(Math.round((Date.now() - t0) / 1000)), 1000);
    return () => window.clearInterval(id);
  }, [decadeCompareLoading]);

  const togglePin = useCallback(
    (row: EvidenceRow) => {
      setPins((p) => {
        const next = p.includes(row.passage_id) ? p.filter((x) => x !== row.passage_id) : [...p, row.passage_id].slice(-2);
        applyState({ q: asked, filters: askedFilters, pins: next, kiosk, offline }, "replace");
        return next;
      });
    },
    [asked, askedFilters, kiosk, offline],
  );

  const clearPins = useCallback(() => {
    setPins([]);
    applyState({ q: asked, filters: askedFilters, pins: [], kiosk, offline }, "replace");
  }, [asked, askedFilters, kiosk, offline]);

  const pinned = pins.map((id) => byId.get(id)).filter((r): r is EvidenceRow => Boolean(r));
  // A two-decade comparison from the timeline takes over the compare slot, ahead of a story or a
  // free pinned pair. decadeResult also covers the honest "no passage in that period" note, which
  // stands in place of the answer for a comparison that could not be formed.
  const decadeResult = decadeCompare !== null || decadeCompareNote !== null || decadeCompareLoading;
  const compare: [EvidenceRow, EvidenceRow] | null = decadeCompare
    ? [decadeCompare.a, decadeCompare.b]
    : storyRows ?? (pinned.length === 2 ? [pinned[0], pinned[1]] : null);
  const showStories = view === null && response === null && status !== "waiting" && status !== "error";
  const salient = response?.answer.coverage.salient_terms ?? [];
  // resultFlagged gates the initial-result interstitial (question + story). The note also
  // folds in a free user-pinned pair's flag, so a pinned comparison shows the same note; a
  // post-hoc pin adds the note without re-gating the result the visitor is already reading.
  const resultFlagged = mergeFlagged(response?.flagged ?? null, storyFlagged);
  const flagged = mergeFlagged(resultFlagged, pinFlagged);
  // The contextual note and its support line belong only where a flagged document or answer is
  // actually shown (a normal answer, a compare pair, or a limited-mode card). On a pure abstention
  // or a coverage-gap refuse nothing is foregrounded, so suppress them there: a suicide crisis line
  // must never appear on a "the record is silent here" result, and the flagship refuse must not put
  // harm-adjacent content on screen (D1). The flagged content stays fully searchable and reachable.
  const abstentionOnly = !!response && response.answer.abstained && !response.degraded && !compare;
  const showContextualNote =
    !!flagged && !abstentionOnly && !decadeCompareLoading && decadeCompareNote === null;
  const busy = status === "waiting";
  // Per-scope, from the active scope's live composition (same source as the strip and subtitle),
  // never the no-scope /health corpus, so the coverage caption reads the active corpus's figure.
  const undatedShare = activeScopeInfo?.composition?.undated?.passage_share ?? null;
  // The "watch it refuse" doorway is scope-aware: the pilot runs q039, microlog runs mq41, both real
  // out-of-record COVID-2020 probes that abstain. It is a real seed example of the active scope,
  // pulled from that scope's /examples, so the card appears only when the question is actually
  // available (a scope without it, or with no examples, shows no refuse card).
  const refuseQid = activeScopeInfo?.name === "microlog" ? "mq41" : "q039";
  const refuseExample = chips.find((c) => c.qid === refuseQid) ?? null;
  // A one-line summary for the collapsed "About this corpus" strip, from the same live per-scope
  // composition the strip itself reads, so the summary and the opened band can never disagree.
  const strip = activeScopeInfo?.composition ?? null;
  const stripWindow = activeScopeInfo?.coverage_window ?? null;
  const corpusSummary =
    activeScopeInfo && strip
      ? `${plural(activeScopeInfo.item_count, "item")}, ${plural(strip.passages, "passage")}` +
        (stripWindow && stripWindow.min_year != null && stripWindow.max_year != null
          ? `, ${stripWindow.min_year} to ${stripWindow.max_year}`
          : "")
      : "corpus facts";

  return (
    <div className="mx-auto max-w-[1100px] px-4 py-6 sm:px-6">
      <a className="skip-link" href="#main-content">Skip to main content</a>
      <Header
        kiosk={kiosk}
        view={view}
        onView={goView}
        onAsk={goAsk}
        scopes={scopesInfo?.scopes ?? null}
        activeScope={initial.current.scope ?? scopesInfo?.default ?? ""}
        onSwitchScope={switchScope}
      />
      <EntryAdvisory />
      {view === "explore" && (
        <ExplorePage
          scopes={scopesInfo?.scopes ?? null}
          examplesByScope={scopeExamples}
          onExploreScope={switchScope}
          onEnterQuestion={enterScopeWithQuestion}
        />
      )}
      {view === "how" && <HowItWorks scope={activeScopeInfo} />}
      {view === "gaps" && <Gaps scope={activeScopeInfo} crisis={scopesInfo?.crisis ?? null} />}
      {view === "sources" && <SourcesPage scopes={scopesInfo?.scopes ?? null} />}
      {view === "map" && <CoverageMap scope={activeScopeInfo} onExplore={exploreProvince} onNav={goView} />}
      {view === "timeline" && (
        <TimelinePage
          scope={activeScopeInfo}
          initialQuestion={asked}
          onDrillDecade={onDrillDecade}
          onCompareDecades={onCompareDecades}
        />
      )}
      {view === "about" && <About scope={activeScopeInfo} />}
      {view === null && (
      <main id="main-content" tabIndex={-1}>
      {showStories && (
        <>
          <section className="my-4" aria-label="What this is">
            <p className="max-w-prose text-base leading-relaxed sm:text-lg">
              Ask a question of Canada's public health record and you can see how the government's own
              wording shifted over the decades, instead of one collapsed summary. Every claim links back
              to the page it came from, so you can check it yourself. When the record is too thin to
              answer, the tool says so and shows you the gap.
            </p>
            <p className="mt-3 max-w-prose border-l-2 border-rule pl-4 text-sm text-ink">
              If the tool makes a claim, you should be able to trace it back to the page that supports it.
            </p>
          </section>
          <StoryGallery stories={stories} loading={storiesLoading} onOpen={openStory} />
          {refuseExample && (
            <p className="mt-6 max-w-prose text-sm text-muted">
              <button
                type="button"
                onClick={() => pick(refuseExample)}
                disabled={busy}
                aria-label={`See the tool decline: ${refuseExample.text}`}
                className="linkish text-ink disabled:opacity-60"
              >
                See it decline
              </button>
              : ask about a year the record does not cover, like 2020, and it shows the gap instead of guessing.
            </p>
          )}
        </>
      )}
      {!offline && (
        <div className={showStories ? "mt-8" : undefined}>
          {showStories && <p className="mb-2 text-sm text-muted">Or ask the record your own question:</p>}
          <AskBar
            question={question}
            filters={filters}
            busy={busy}
            kiosk={kiosk}
            scope={activeScopeInfo}
            onQuestion={setQuestion}
            onFilters={setFilters}
            onAsk={onAsk}
          />
        </div>
      )}
      {!showStories && (
        <ExampleChips
          chips={chips}
          activeText={asked}
          onPick={pick}
          disabled={busy}
          collapsed={chipsCollapsed && response !== null}
          onToggle={() => setChipsCollapsed((c) => !c)}
          kiosk={kiosk}
        />
      )}
      <AnswerSkeleton status={status} elapsed={elapsed} passages={activeScopeInfo?.composition?.passages ?? null} />
      {showStories && (
        <details className="evidence-disclosure">
          <summary>About this corpus: {corpusSummary}</summary>
          <CorpusStrip scope={activeScopeInfo ?? null} />
        </details>
      )}

      {status === "error" && error && <ErrorCard detail={error} />}

      {response && (
        needsInterstitial(resultFlagged) && !flaggedAck ? (
          <Interstitial flagged={resultFlagged!} onContinue={() => setFlaggedAck(true)} onBack={goHome} />
        ) : (
        <>
          {showContextualNote && <ContextualNote flagged={flagged!} />}
          {activeScopeInfo && <SourceLine scope={activeScopeInfo} />}
          {askedFilters.jurisdiction &&
            PROVINCE_SLUGS.has(askedFilters.jurisdiction) &&
            activeScopeInfo?.composition?.jurisdiction_is_floor && (
              <p className="text-sm text-muted">
                Filtered to {askedFilters.jurisdiction.replace(/_/g, " ")}: these are proxy-derived
                counts, a floor, not precise per-province coverage.
              </p>
            )}
          {decadeResult ? (
            // A two-decade comparison from the timeline: the compare view is the result, so the
            // answer, trail, and coverage step aside. compare is set when both periods yielded a
            // passage; the note stands in when one did not.
            <>
              <p className="mt-2 font-sans text-xs uppercase tracking-wide text-muted">
                Two decades of the record, side by side
              </p>
              {decadeCompareLoading ? (
                <SkeletonBody
                  heading="Two decades of the record, side by side"
                  caption={`Looking for a passage from each decade for this question. ${decadeElapsed} s.`}
                />
              ) : compare ? (
                <CompareView
                  a={compare[0]}
                  b={compare[1]}
                  salientTerms={decadeCompare?.terms ?? salient}
                  onOpen={setDrawer}
                  onUnpin={clearDecadeCompare}
                  onClose={clearDecadeCompare}
                />
              ) : (
                <div className="card mt-4">
                  <p className="leading-relaxed">{decadeCompareNote}</p>
                  <div className="mt-3 flex flex-wrap gap-2">
                    {decadeRetry && (
                      <button
                        type="button"
                        className="chip chip-primary"
                        onClick={() => onCompareDecades(asked, decadeRetry.a, decadeRetry.b)}
                      >
                        Try the comparison again
                      </button>
                    )}
                    <button type="button" className="chip" onClick={clearDecadeCompare}>
                      Back to the answer
                    </button>
                  </div>
                </div>
              )}
            </>
          ) : (
            <>
              {response.degraded ? (
                <>
                  <LimitedModeCard answer={response.answer} degraded={response.degraded} />
                  <CoveragePanel coverage={coverage} undatedShare={undatedShare} explanation scope={activeScopeInfo} />
                </>
              ) : response.answer.abstained ? (
                <>
                  <AbstentionCard answer={response.answer} />
                  <CoveragePanel coverage={coverage} undatedShare={undatedShare} explanation scope={activeScopeInfo} />
                </>
              ) : (
                <AnswerCard answer={response.answer} byId={byId} onOpen={setDrawer} />
              )}

              {compare && (
                <CompareView
                  a={compare[0]}
                  b={compare[1]}
                  salientTerms={salient}
                  caption={storyRows ? storyCaption ?? undefined : undefined}
                  onOpen={setDrawer}
                  onUnpin={storyRows ? () => { setStoryRows(null); setStoryCaption(null); } : togglePin}
                  onClose={storyRows ? () => { setStoryRows(null); setStoryCaption(null); } : clearPins}
                />
              )}

              {/* The evidence trail is the point of the tool, so it is open by default (keyed per
                  answer so a new question re-opens it); the summary stays a working control to
                  collapse it for readers who want to focus on the answer. */}
              <details key={asked} className="evidence-disclosure" open>
                <summary>
                  {response.answer.abstained
                    ? `Nearest evidence: ${plural(response.evidence.length, "passage")} by decade. Collapse to focus on the answer.`
                    : `Full evidence trail and coverage: ${plural(response.evidence.length, "passage")} by decade. Collapse to focus on the answer.`}
                </summary>
                <EvidenceTrail
                  rows={response.evidence}
                  salientTerms={salient}
                  pinned={pins}
                  heading={response.degraded ? "The record for your question" : response.answer.abstained ? "Nearest evidence, not an answer" : "Evidence trail"}
                  matched={matched}
                  onOpen={setDrawer}
                  onPin={togglePin}
                  source={activeScopeInfo}
                />
                {!response.answer.abstained && <CoveragePanel coverage={coverage} undatedShare={undatedShare} scope={activeScopeInfo} />}
              </details>
            </>
          )}
        </>
        )
      )}
      </main>
      )}

      <Footer onAbout={() => goView("about")} />
      <PageDrawer row={drawer} onClose={() => setDrawer(null)} source={activeScopeInfo} offline={offline || kiosk} />
    </div>
  );
}
