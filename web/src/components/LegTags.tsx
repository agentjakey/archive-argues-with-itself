import type { EvidenceRow } from "../types";

/** Which retrieval leg surfaced the passage. Text, not color. */
export function LegTags({ row }: { row: Pick<EvidenceRow, "bm25_rank" | "dense_rank"> }) {
  return (
    <span className="inline-flex gap-1 text-xs text-muted font-sans">
      {row.bm25_rank != null && <span className="border border-rule px-1.5 rounded-sm">lexical</span>}
      {row.dense_rank != null && <span className="border border-rule px-1.5 rounded-sm">semantic</span>}
    </span>
  );
}
