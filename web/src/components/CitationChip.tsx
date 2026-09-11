import { useId, useState, type KeyboardEvent } from "react";
import { chipLabel } from "../lib/format";
import type { EvidenceRow } from "../types";

interface Props {
  row: EvidenceRow | undefined;
  passageId: string;
  onOpen: (row: EvidenceRow) => void;
}

/** Claim-adjacent citation. Focus or first tap reveals snippet and metadata;
 *  Enter, or a second tap, opens the Page drawer. */
export function CitationChip({ row, passageId, onOpen }: Props) {
  const [shown, setShown] = useState(false);
  const popId = useId();

  if (!row) {
    return <span className="chip font-mono text-xs">{passageId}</span>;
  }

  const open = () => onOpen(row);
  const onKey = (e: KeyboardEvent<HTMLButtonElement>) => {
    if (e.key === "Enter") {
      e.preventDefault();
      open();
    }
  };
  const onClick = () => {
    if (shown) open();
    else setShown(true);
  };

  return (
    <span className="relative inline-block align-baseline mx-1">
      <button
        type="button"
        className="chip"
        aria-label={`Citation: ${chipLabel(row)}. Enter opens the page.`}
        aria-describedby={shown ? popId : undefined}
        aria-expanded={shown}
        onFocus={() => setShown(true)}
        onBlur={() => setShown(false)}
        onKeyDown={onKey}
        onClick={onClick}
      >
        <span className="font-mono text-xs">{row.item_id}</span>
        <span className="ml-2">{row.printed_page ? `p. ${row.printed_page}` : `leaf ${row.leaf_index}`}</span>
      </button>
      {shown && (
        <span
          id={popId}
          role="tooltip"
          className="absolute left-0 top-full z-10 mt-1 w-[min(28rem,80vw)] card text-sm"
        >
          <span className="block font-sans text-muted text-xs">
            {chipLabel(row)} <span className="font-mono">leaf {row.leaf_index}</span>
          </span>
          <span className="block excerpt mt-1">{row.snippet}</span>
        </span>
      )}
    </span>
  );
}
