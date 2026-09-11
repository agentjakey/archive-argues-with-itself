import type { FormEvent } from "react";
import type { DocType, Filters, Jurisdiction, Period } from "../types";

const PERIODS: Period[] = ["pre-1960", "1960s", "1970s", "1980s", "1990s", "2000s", "post-2009", "undated"];
const JURISDICTIONS: Jurisdiction[] = ["federal", "ontario", "alberta", "international", "unknown"];
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
  onQuestion: (q: string) => void;
  onFilters: (f: Filters) => void;
  onAsk: () => void;
}

/** Controlled by App so the URL can restore it. Selects sized to content, one row,
 *  stacking below 700px. Filters are hidden in kiosk mode. */
export function AskBar({ question, filters, busy, kiosk, onQuestion, onFilters, onAsk }: Props) {
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

  return (
    <section aria-label="Ask" className="mb-2">
      <form onSubmit={submit} className="flex flex-col gap-3">
        <label className="sr-only" htmlFor="question">
          Question
        </label>
        <div className="flex gap-2">
          <input
            id="question"
            className="flex-1 min-w-0 border border-ink bg-sheet px-3 rounded-sm font-sans"
            placeholder="Ask about the public-health record, 1960 to 2009"
            value={question}
            onChange={(e) => onQuestion(e.target.value)}
            disabled={busy}
            autoComplete="off"
          />
          <button type="submit" className="chip bg-ink text-paper border-ink px-5" disabled={busy || !question.trim()}>
            Ask
          </button>
        </div>
        {!kiosk && (
          <div className="flex flex-col min-[700px]:flex-row gap-2">
            <Select label="Period" value={filters.period ?? ""} options={PERIODS} onChange={(v) => set("period", v)} disabled={busy} />
            <Select label="Jurisdiction" value={filters.jurisdiction ?? ""} options={JURISDICTIONS} onChange={(v) => set("jurisdiction", v)} disabled={busy} />
            <Select label="Document type" value={filters.doc_type ?? ""} options={DOC_TYPES} onChange={(v) => set("doc_type", v)} disabled={busy} />
          </div>
        )}
      </form>
    </section>
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
        className="w-auto border border-rule bg-sheet px-2 rounded-sm text-ink font-sans"
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
