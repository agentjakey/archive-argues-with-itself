import { useEffect, useState, type FormEvent } from "react";
import { onChallengeState, SLOT_ID, type ChallengeState } from "../lib/turnstile";
import type { DocType, Filters, Jurisdiction, Period, ScopeInfo } from "../types";

const PERIODS: Period[] = ["pre-1960", "1960s", "1970s", "1980s", "1990s", "2000s", "post-2009", "undated"];
const JURISDICTIONS: Jurisdiction[] = [
  "federal",
  "ontario",
  "quebec",
  "british_columbia",
  "alberta",
  "manitoba",
  "saskatchewan",
  "nova_scotia",
  "new_brunswick",
  "newfoundland",
  "prince_edward_island",
  "yukon",
  "northwest_territories",
  "nunavut",
  "international",
  "unknown",
];
const DOC_TYPES: DocType[] = [
  "royal_commission",
  "commission",
  "annual_report",
  "statistical_report",
  "standing_committee",
  "board_or_appeal",
  "other",
];

interface Props {
  question: string;
  filters: Filters;
  busy: boolean;
  kiosk: boolean;
  scope?: ScopeInfo | null;   // the active corpus, so the placeholder names its real window, never a hardcoded one
  onQuestion: (q: string) => void;
  onFilters: (f: Filters) => void;
  onAsk: () => void;
  onFocusQuestion?: () => void;   // the question box got focus: a good moment to start the engine
  /** "hero" on the opening screen (large, centered); "compact" above a result, kept in view. */
  variant?: "hero" | "compact";
}

function activeFilterCount(f: Filters): number {
  return Object.values(f).filter(Boolean).length;
}

/** The question box. Controlled by App so the URL can restore it. The filters fold under a
 *  "Refine" disclosure so the box stays one clean line; they are hidden in kiosk mode. */
export function AskBar({
  question,
  filters,
  busy,
  kiosk,
  scope,
  onQuestion,
  onFilters,
  onAsk,
  onFocusQuestion,
  variant = "compact",
}: Props) {
  const cw = scope?.coverage_window;
  // The placeholder reads the active corpus's coverage window, never a hardcoded one; before the
  // corpus loads it drops the years rather than guess.
  const years = cw && cw.min_year != null && cw.max_year != null ? `, ${cw.min_year} to ${cw.max_year}` : "";
  const placeholder = variant === "hero" ? "Ask a question" : `Ask another question${years}`;
  const [challenge, setChallenge] = useState<ChallengeState>("idle");
  useEffect(() => onChallengeState(setChallenge), []);
  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (question.trim()) onAsk();
  };

  const set = <K extends keyof Filters>(key: K, value: string) => {
    const next = { ...filters };
    if (value) (next as Record<string, unknown>)[key] = value;
    else delete next[key];
    onFilters(next);
  };
  const nFilters = activeFilterCount(filters);
  const hero = variant === "hero";

  return (
    <section aria-label="Ask a question" className={hero ? "askbar askbar-hero" : "askbar askbar-compact"}>
      <form onSubmit={submit} role="search" aria-label="Ask the record">
        <label className="sr-only" htmlFor="question">
          Your question about the record{years}
        </label>
        <div className="search-field">
          <SearchIcon />
          <input
            id="question"
            type="search"
            enterKeyHint="search"
            className="search-input"
            placeholder={placeholder}
            value={question}
            onChange={(e) => onQuestion(e.target.value)}
            onFocus={onFocusQuestion}
            disabled={busy}
            autoComplete="off"
            spellCheck
            maxLength={300}
          />
          <button type="submit" className="search-submit" disabled={busy || !question.trim()}>
            {busy ? "Asking" : "Ask"}
          </button>
        </div>
        {/* The person check (Cloudflare Turnstile) draws here. Most visitors never see it; when
            Cloudflare asks for a click, it appears right under the button that was pressed. */}
        <div id={SLOT_ID} className="turnstile-slot" />
        <p className={challenge === "interactive" ? "mt-2 text-sm text-ink" : "sr-only"} role="status" aria-live="polite">
          {challenge === "interactive"
            ? "Before your question is sent, Cloudflare asks you to confirm you are a person. Answer the check just above."
            : ""}
        </p>
        {!kiosk && (
          // The selects are always in the DOM (a native disclosure), so a set filter still applies
          // and restores from the URL.
          <details className="filters">
            <summary className="filters-summary">
              Refine by period, place or document type{nFilters > 0 ? ` (${nFilters} set)` : ""}
            </summary>
            <div className="mt-2 flex flex-col min-[700px]:flex-row min-[700px]:flex-wrap gap-2">
              <Select label="Period" value={filters.period ?? ""} options={PERIODS} onChange={(v) => set("period", v)} disabled={busy} />
              <Select label="Place" value={filters.jurisdiction ?? ""} options={JURISDICTIONS} onChange={(v) => set("jurisdiction", v)} disabled={busy} />
              <Select label="Document type" value={filters.doc_type ?? ""} options={DOC_TYPES} onChange={(v) => set("doc_type", v)} disabled={busy} />
            </div>
            <div className="mt-2 flex flex-col min-[700px]:flex-row gap-2">
              <YearInput label="From year" value={filters.year_from ?? ""} onChange={(v) => set("year_from", v)} disabled={busy} />
              <YearInput label="To year" value={filters.year_to ?? ""} onChange={(v) => set("year_to", v)} disabled={busy} />
              <YearInput label="As of year" value={filters.as_of_year ?? ""} onChange={(v) => set("as_of_year", v)} disabled={busy} />
            </div>
            <p className="mt-1 text-sm text-muted">
              Years use the catalogue date, so a year filter leaves out undated documents.
              {nFilters > 0 && (
                <>
                  {" "}
                  <button type="button" className="linkish" onClick={() => onFilters({})} disabled={busy}>
                    Clear all filters
                  </button>
                </>
              )}
            </p>
          </details>
        )}
      </form>
    </section>
  );
}

function SearchIcon() {
  return (
    <svg className="search-icon" width="20" height="20" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
      <circle cx="10.5" cy="10.5" r="6" fill="none" stroke="currentColor" strokeWidth="1.8" />
      <path d="M15 15l5 5" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  );
}

interface YearInputProps {
  label: string;
  value: string;
  onChange: (v: string) => void;
  disabled?: boolean;
}

/** A four-digit year. Only a complete year (or nothing) is passed up, so a half-typed year never
 *  reaches the engine, which would refuse it. */
function YearInput({ label, value, onChange, disabled }: YearInputProps) {
  const id = `year-${label.toLowerCase().replace(/\s+/g, "-")}`;
  const [draft, setDraft] = useState(value);
  useEffect(() => setDraft(value), [value]);
  return (
    <label htmlFor={id} className="flex items-center gap-2 text-sm text-muted">
      {label}
      <input
        id={id}
        className="w-20 border border-line bg-sheet px-2 rounded-sm text-ink font-sans"
        inputMode="numeric"
        pattern="[0-9]{4}"
        maxLength={4}
        placeholder="any"
        value={draft}
        onChange={(e) => {
          const next = e.target.value.replace(/[^0-9]/g, "").slice(0, 4);
          setDraft(next);
          if (next === "" || next.length === 4) onChange(next);
        }}
        disabled={disabled}
      />
    </label>
  );
}

interface SelectProps {
  label: string;
  value: string;
  options: string[];
  onChange: (v: string) => void;
  disabled?: boolean;
}

function Select({ label, value, options, onChange, disabled }: SelectProps) {
  const id = `sel-${label.toLowerCase().replace(/\s+/g, "-")}`;
  return (
    <label htmlFor={id} className="flex items-center gap-2 text-sm text-muted">
      {label}
      <select
        id={id}
        className="w-auto border border-line bg-sheet px-2 rounded-sm text-ink font-sans"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        disabled={disabled}
      >
        <option value="">any</option>
        {options.map((o) => (
          <option key={o} value={o}>
            {o.replace(/_/g, " ")}
          </option>
        ))}
      </select>
    </label>
  );
}
