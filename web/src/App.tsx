import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AbstentionCard } from "./components/AbstentionCard";
import { AnswerCard } from "./components/AnswerCard";
import { AskBar } from "./components/AskBar";
import { CompareView } from "./components/CompareView";
import { CoveragePanel } from "./components/CoveragePanel";
import { ErrorCard } from "./components/ErrorCard";
import { EvidenceTrail } from "./components/EvidenceTrail";
import { ExampleChips } from "./components/ExampleChips";
import { Footer } from "./components/Footer";
import { Header } from "./components/Header";
import { PageDrawer } from "./components/PageDrawer";
import { WaitingLabel } from "./components/WaitingLabel";
import { useAsk } from "./hooks/useAsk";
import { useCoverage } from "./hooks/useCoverage";
import { useExamples } from "./hooks/useExamples";
import { useHealth } from "./hooks/useHealth";
import { useKiosk } from "./hooks/useKiosk";
import { About } from "./components/pages/About";
import { Gaps } from "./components/pages/Gaps";
import { HowItWorks } from "./components/pages/HowItWorks";
import { Stories } from "./components/Stories";
import { useAttractLoop } from "./hooks/useAttractLoop";
import { useStories } from "./hooks/useStories";
import { applyState, readState, type View } from "./lib/urlstate";
import type { EvidenceRow, Example, Filters, Story } from "./types";

export default function App() {
  const kiosk = useKiosk();
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
  const stories = useStories();
  const coverage = useCoverage(asked, askedFilters);

  const goView = useCallback(
    (next: View | null) => {
      setView(next);
      applyState({ q: asked, filters: askedFilters, pins, kiosk, view: next ?? undefined }, "push");
      window.scrollTo({ top: 0 });
    },
    [asked, askedFilters, pins, kiosk],
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
      setDrawer(null);
      setChipsCollapsed(true);
      applyState({ q, filters: f, pins: [], kiosk }, "push");
      void run({ question: q, filters: f });
    },
    [run, kiosk],
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
      window.scrollTo({ top: 0 });
    },
    [ask],
  );

  // Kiosk attract loop: idle 60 s -> cycle stories; any touch -> back to the home screen.
  const goHome = useCallback(() => {
    window.location.assign(`${window.location.pathname}${kiosk ? "?kiosk=1" : ""}`);
  }, [kiosk]);
  useAttractLoop({ enabled: kiosk, stories, onShow: openStory, onHome: goHome });

  const pick = useCallback(
    (e: Example) => {
      setQuestion(e.text);
      setFilters(e.filters ?? {});
      ask(e.text, e.filters ?? {});
    },
    [ask],
  );

  const togglePin = useCallback(
    (row: EvidenceRow) => {
      setPins((p) => {
        const next = p.includes(row.passage_id) ? p.filter((x) => x !== row.passage_id) : [...p, row.passage_id].slice(-2);
        applyState({ q: asked, filters: askedFilters, pins: next, kiosk }, "replace");
        return next;
      });
    },
    [asked, askedFilters, kiosk],
  );

  const clearPins = useCallback(() => {
    setPins([]);
    applyState({ q: asked, filters: askedFilters, pins: [], kiosk }, "replace");
  }, [asked, askedFilters, kiosk]);

  const pinned = pins.map((id) => byId.get(id)).filter((r): r is EvidenceRow => Boolean(r));
  const compare: [EvidenceRow, EvidenceRow] | null =
    storyRows ?? (pinned.length === 2 ? [pinned[0], pinned[1]] : null);
  const showStories = view === null && response === null && status !== "waiting" && status !== "error";
  const salient = response?.answer.coverage.salient_terms ?? [];
  const busy = status === "waiting";
  const undatedShare = health?.corpus.undated_share ?? null;

  return (
    <div className="mx-auto max-w-[1100px] px-4 py-6 sm:px-6">
      <Header corpus={health?.corpus ?? null} kiosk={kiosk} view={view} onView={goView} />
      {view === "how" && <HowItWorks />}
      {view === "gaps" && <Gaps />}
      {view === "about" && <About />}
      {view === null && (
      <>
      <AskBar
        question={question}
        filters={filters}
        busy={busy}
        kiosk={kiosk}
        onQuestion={setQuestion}
        onFilters={setFilters}
        onAsk={onAsk}
      />
      <ExampleChips
        chips={chips}
        activeText={asked}
        onPick={pick}
        disabled={busy}
        collapsed={chipsCollapsed && response !== null}
        onToggle={() => setChipsCollapsed((c) => !c)}
        kiosk={kiosk}
      />
      <WaitingLabel status={status} elapsed={elapsed} completion={completion} passages={health?.corpus.passages ?? null} />
      {showStories && <Stories stories={stories} onOpen={openStory} />}

      {status === "error" && error && (
        <main>
          <ErrorCard detail={error} />
        </main>
      )}

      {response && (
        <main>
          {response.answer.abstained ? (
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
              onUnpin={storyRows ? () => setStoryRows(null) : togglePin}
              onClose={storyRows ? () => setStoryRows(null) : clearPins}
            />
          )}

          <EvidenceTrail
            rows={response.evidence}
            salientTerms={salient}
            pinned={pins}
            heading={response.answer.abstained ? "Nearest evidence, not an answer" : "Evidence trail"}
            matched={matched}
            onOpen={setDrawer}
            onPin={togglePin}
          />
          {!response.answer.abstained && <CoveragePanel coverage={coverage} undatedShare={undatedShare} />}
        </main>
      )}
      </>
      )}

      <Footer onAbout={() => goView("about")} />
      <PageDrawer row={drawer} onClose={() => setDrawer(null)} />
    </div>
  );
}
