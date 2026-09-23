import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AbstentionCard } from "./components/AbstentionCard";
import { AnswerCard } from "./components/AnswerCard";
import { LimitedModeCard } from "./components/LimitedModeCard";
import { AskBar } from "./components/AskBar";
import { AttractHero } from "./components/AttractHero";
import { QuestionTiles } from "./components/QuestionTiles";
import { CompareView } from "./components/CompareView";
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
import { WaitingLabel } from "./components/WaitingLabel";
import { useAsk } from "./hooks/useAsk";
import { useCoverage } from "./hooks/useCoverage";
import { useExamples } from "./hooks/useExamples";
import { useHealth } from "./hooks/useHealth";
import { useKiosk, useOffline } from "./hooks/useKiosk";
import { About } from "./components/pages/About";
import { Gaps } from "./components/pages/Gaps";
import { HowItWorks } from "./components/pages/HowItWorks";
import { SourcesPage } from "./components/pages/Sources";
import { ExplorePage } from "./components/pages/Explore";
import { TimelinePage } from "./components/pages/Timeline";
import { SourceLine } from "./components/SourceLine";
import { CoverageMap } from "./components/CoverageMap";
import { Stories } from "./components/Stories";
import { useAttractLoop } from "./hooks/useAttractLoop";
import { useScopes } from "./hooks/useScopes";
import { useScopeExamples } from "./hooks/useScopeExamples";
import { useStories } from "./hooks/useStories";
import { flag as apiFlag } from "./lib/api";
import { TILE_QIDS } from "./lib/attract";
import { applyState, readState, type View } from "./lib/urlstate";
import { mergeFlagged, needsInterstitial } from "./lib/sensitivity";
import { PROVINCE_SLUGS } from "./lib/coverage";
import { periodOfRow } from "./lib/timeline";
import type { EvidenceRow, Example, Filters, Flagged, Period, Story } from "./types";

export default function App() {
  const kiosk = useKiosk();
  const offline = useOffline();   // ?offline=1: no ask box, cached questions and stories only
  const health = useHealth();
  const chips = useExamples();
  const { status, elapsed, response, error, run, completion } = useAsk();

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
  const stories = useStories();
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

  // Back/forward buttons move between the ask view and the reading pages.
  useEffect(() => {
    const onPop = () => setView(readState(window.location.search).view ?? null);
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);

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
    // Idempotent: if already on the clean home for this scope, do not reload -- so a no-story scope
    // (microlog) resets to home once on idle, then rests without re-blinking every idle interval.
    if (window.location.pathname + window.location.search === target) return;
    window.location.assign(target);
  }, [kiosk, offline, scopesInfo]);
  const idleMs = useMemo(() => {
    const v = Number(idleParam.current);
    return Number.isFinite(v) && v > 0 ? v * 1000 : undefined;
  }, []);
  useAttractLoop({ enabled: kiosk, stories, onShow: openStory, onHome: goHome, idleMs });

  // Switch corpora with a full reload into a clean home for the chosen scope: no q/filters/
  // pins/view/story carried over, so no result from the other corpus can linger. Only the
  // venue launch flags (kiosk/offline/idle) are preserved. The pilot is the default and
  // carries no ?scope, so its URL stays exactly as before.
  const switchScope = useCallback(
    (name: string) => {
      const def = scopesInfo?.default ?? "";
      const params = new URLSearchParams();
      if (name && name !== def) params.set("scope", name);
      if (kiosk) params.set("kiosk", "1");
      if (offline) params.set("offline", "1");
      if (idleParam.current) params.set("idle", idleParam.current);
      const qs = params.toString();
      window.location.assign(`${window.location.pathname}${qs ? `?${qs}` : ""}`);
    },
    [scopesInfo, kiosk, offline],
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
      window.scrollTo({ top: 0 });
    },
    [ask],
  );

  // Resolve a pending two-decade comparison once its answer's pool is in. Picks the top-ranked pool
  // passage in each period (period_of matches the histogram's buckets). If either period has no
  // retrieved passage for the question, say so honestly rather than inventing one.
  useEffect(() => {
    if (!pendingDecadeCompare || !response) return;
    const { a, b } = pendingDecadeCompare;
    const pool = response.evidence;
    const rowA = pool.find((r) => periodOfRow(r) === a) ?? null;
    const rowB = pool.find((r) => periodOfRow(r) === b) ?? null;
    if (rowA && rowB) {
      setDecadeCompare({ a: rowA, b: rowB, terms: response.answer.coverage.salient_terms ?? [] });
      setDecadeCompareNote(null);
    } else {
      setDecadeCompare(null);
      const missing = [!rowA ? a : null, !rowB ? b : null].filter(Boolean).join(" and ");
      setDecadeCompareNote(
        `The record surfaced no passage in ${missing} for this question, so there is nothing to compare there. ` +
          `That period may be sparse for this question; try another decade or a different question.`,
      );
    }
    setPendingDecadeCompare(null);
  }, [response, pendingDecadeCompare]);

  const clearDecadeCompare = useCallback(() => {
    setDecadeCompare(null);
    setDecadeCompareNote(null);
    setPendingDecadeCompare(null);
  }, []);

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
  const decadeResult = decadeCompare !== null || decadeCompareNote !== null;
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
  const busy = status === "waiting";
  const undatedShare = health?.corpus.undated_share ?? null;
  // Attract tiles: the curated non-flagged cached questions, in config order, pulled from
  // /examples so their text and filters match the cache exactly (offline-instant on tap).
  const tiles = TILE_QIDS.map((id) => chips.find((c) => c.qid === id)).filter((e): e is Example => Boolean(e));

  return (
    <div className="mx-auto max-w-[1100px] px-4 py-6 sm:px-6">
      <Header
        corpus={health?.corpus ?? null}
        kiosk={kiosk}
        view={view}
        onView={goView}
        scopes={scopesInfo?.scopes ?? null}
        activeScope={initial.current.scope ?? scopesInfo?.default ?? ""}
        activeScopeInfo={activeScopeInfo}
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
      {view === "how" && <HowItWorks />}
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
      {view === "about" && <About />}
      {view === null && (
      <>
      {showStories && <AttractHero />}
      {showStories && <QuestionTiles tiles={tiles} onPick={pick} disabled={busy} />}
      {!offline && (
        <div className={showStories ? "mt-6" : undefined}>
          {showStories && <p className="mb-2 text-sm text-muted">Or ask your own question:</p>}
          <AskBar
            question={question}
            filters={filters}
            busy={busy}
            kiosk={kiosk}
            onQuestion={setQuestion}
            onFilters={setFilters}
            onAsk={onAsk}
          />
        </div>
      )}
      {showStories && (
        <p className="mt-3 text-muted">Open a story below to see two pages from the record, years apart.</p>
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
      <WaitingLabel status={status} elapsed={elapsed} completion={completion} passages={health?.corpus.passages ?? null} />
      {showStories && <Stories stories={stories} onOpen={openStory} />}

      {status === "error" && error && (
        <main>
          <ErrorCard detail={error} />
        </main>
      )}

      {response && (
        needsInterstitial(resultFlagged) && !flaggedAck ? (
          <Interstitial flagged={resultFlagged!} onContinue={() => setFlaggedAck(true)} onBack={goHome} />
        ) : (
        <main>
          {flagged && <ContextualNote flagged={flagged} />}
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
              {compare ? (
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
                  <button type="button" className="chip mt-3" onClick={clearDecadeCompare}>
                    Back to the answer
                  </button>
                </div>
              )}
            </>
          ) : (
            <>
              {response.degraded ? (
                <>
                  <LimitedModeCard answer={response.answer} degraded={response.degraded} />
                  <CoveragePanel coverage={coverage} undatedShare={undatedShare} explanation />
                </>
              ) : response.answer.abstained ? (
                <>
                  <AbstentionCard answer={response.answer} />
                  <CoveragePanel coverage={coverage} undatedShare={undatedShare} explanation />
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
              {!response.answer.abstained && <CoveragePanel coverage={coverage} undatedShare={undatedShare} />}
            </>
          )}
        </main>
        )
      )}
      </>
      )}

      <Footer onAbout={() => goView("about")} />
      <PageDrawer row={drawer} onClose={() => setDrawer(null)} source={activeScopeInfo} offline={offline || kiosk} />
    </div>
  );
}
