import type { Example } from "../types";

interface Props {
  chips: Example[];
  activeText: string;
  onPick: (e: Example) => void;
  disabled?: boolean;
  /** Collapsed behind "More questions" once a result exists (never in kiosk). */
  collapsed: boolean;
  onToggle: () => void;
  kiosk: boolean;
}

export function ExampleChips({ chips, activeText, onPick, disabled, collapsed, onToggle, kiosk }: Props) {
  if (!chips.length) return null;
  if (collapsed && !kiosk) {
    return (
      <div className="mt-3">
        <button type="button" className="chip" onClick={onToggle} aria-expanded={false}>
          More questions
        </button>
      </div>
    );
  }
  return (
    <div className="mt-3">
      <div className="flex flex-wrap gap-2" aria-label="Example questions">
        {chips.map((e) => {
          const active = e.text === activeText;
          return (
            <button
              key={e.qid}
              type="button"
              className="chip"
              aria-pressed={active}
              disabled={disabled}
              onClick={() => onPick(e)}
              title={e.gold === "abstain" ? "The record is expected to be thin here" : undefined}
            >
              {e.text}
              {e.gold === "abstain" && <span className="ml-2 text-xs opacity-80">(thin record)</span>}
            </button>
          );
        })}
      </div>
      {!kiosk && !collapsed && activeText && (
        <button type="button" className="mt-2 text-sm text-muted underline min-h-[44px]" onClick={onToggle}>
          Fewer questions
        </button>
      )}
    </div>
  );
}
