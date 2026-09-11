import { useId, useState, type KeyboardEvent } from "react";
import { chipLabel } from "../lib/format";
import type { EvidenceRow } from "../types";

interface Props {
  n: number;
  row: EvidenceRow | undefined;
  passageId: string;
  onOpen: (row: EvidenceRow) => void;
}

/** Numbered citation mark [n]. Focus or first tap reveals the excerpt popover;
 *  Enter, or a second tap, opens the Page drawer. */
export function CitationMark({ n, row, passageId, onOpen }: Props) {
  const [shown, setShown] = useState(false);
  const popId = useId();

  if (!row) {
    return (
      <sup className="mark" title={passageId}>
        [{n}]
      </sup>
    );
  }

  const open = () => onOpen(row);
  const onKey = (e: KeyboardEvent<HTMLButtonElement>) => {
    if (e.key === "Enter") {
      e.preventDefault();
      open();
    }
  };

  return (
    <span className="relative inline-block">
      <button
        type="button"
        className="mark"
        aria-label={`Citation ${n}: ${chipLabel(row)}. Enter opens the page.`}
        aria-describedby={shown ? popId : undefined}
        aria-expanded={shown}
        onFocus={() => setShown(true)}
        onBlur={() => setShown(false)}
        onKeyDown={onKey}
        onClick={() => (shown ? open() : setShown(true))}
      >
        [{n}]
      </button>
      {shown && (
        <span id={popId} role="tooltip" className="popover">
          <span className="block text-sm text-muted">
            {chipLabel(row)} <span className="font-mono">{row.item_id}</span>
          </span>
          <span className="block excerpt mt-1">{row.snippet}</span>
        </span>
      )}
    </span>
  );
}
