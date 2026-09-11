import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AbstentionCard } from "./components/AbstentionCard";
import { AnswerCard } from "./components/AnswerCard";
import { AskBar } from "./components/AskBar";
import { CompareView } from "./components/CompareView";
import { CoveragePanel } from "./components/CoveragePanel";
import { ErrorCard } from "./components/ErrorCard";
import { EvidenceTrail } from "./components/EvidenceTrail";
import { ExampleChips } from "./components/ExampleChips";
import { Header } from "./components/Header";
import { PageDrawer } from "./components/PageDrawer";
import { WaitingLabel } from "./components/WaitingLabel";
import { useAsk } from "./hooks/useAsk";
import { useExamples } from "./hooks/useExamples";
import { useHealth } from "./hooks/useHealth";
import { useKiosk } from "./hooks/useKiosk";
import { applyState, readState } from "./lib/urlstate";
import type { EvidenceRow, Example, Filters } from "./types";

export default function App() {
  const kiosk = useKiosk();
  const health = useHealth();
  const chips = useExamples();
  const { status, elapsed, response, error, run, completion } = useAsk();

  const initial = useRef(readState(window.location.search));
  const [question, setQuestion] = useState(initial.current.q);
  const [filters, setFilters] = useState<Filters>(initial.current.filters);
  const [asked, setAsked] = useState(initial.current.q);
  const [pins, setPins] = useState<string[]>(initial.current.pins);
  const [drawer, setDrawer] = useState<EvidenceRow | null>(null);
  const [chipsCollapsed, setChipsCollapsed] = useState(false);

  // Restore from the URL on load and run the ask.
  useEffect(() => {
    if (initial.current.q) void run({ question: initial.current.q, filters: initial.current.filters });
  }, [run]);

  const byId = useMemo(() => {
    const m = new Map<string, EvidenceRow>();
    response?.evidence.forEach((r) => m.set(r.passage_id, r));
    return m;
  }, [response]);

  const ask = useCallback(
    (q: string, f: Filters) => {
      setAsked(q);
      setPins([]);
      setDrawer(null);
      setChipsCollapsed(true);
      applyState({ q, filters: f, pins: [], kiosk }, "push");
      void run({ question: q, filters: f });
    },
    [run, kiosk],
  );

  const onAsk = useCallback(() => ask(question.trim(), filters), [ask, question, filters]);

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
        applyState({ q: asked, filters, pins: next, kiosk }, "replace");
        return next;
      });
    },
    [asked, filters, kiosk],
  );

  const clearPins = useCallback(() => {
    setPins([]);
    applyState({ q: asked, filters, pins: [], kiosk }, "replace");
  }, [asked, filters, kiosk]);

  const pinned = pins.map((id) => byId.get(id)).filter((r): r is EvidenceRow => Boolean(r));
  const salient = response?.answer.coverage.salient_terms ?? [];
  const busy = status === "waiting";

  return (
    <div className="mx-auto max-w-[1100px] px-4 py-6 sm:px-6">
      <Header corpus={health?.corpus ?? null} kiosk={kiosk} />
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

      {status === "error" && error && (
        <main>
          <ErrorCard detail={error} />
        </main>
      )}

      {response && (
        <main>
          {response.answer.abstained ? (
            <AbstentionCard answer={response.answer} />
          ) : (
            <AnswerCard answer={response.answer} byId={byId} onOpen={setDrawer} />
          )}

          {pinned.length === 2 && (
            <CompareView a={pinned[0]} b={pinned[1]} salientTerms={salient} onUnpin={togglePin} onClose={clearPins} />
          )}

          <EvidenceTrail
            rows={response.evidence}
            salientTerms={salient}
            pinned={pins}
            heading={response.answer.abstained ? "Nearest evidence, not an answer" : "Evidence trail"}
            onOpen={setDrawer}
            onPin={togglePin}
          />
          <CoveragePanel />
        </main>
      )}

      <PageDrawer row={drawer} onClose={() => setDrawer(null)} />
    </div>
  );
}
