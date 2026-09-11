import type { Sentence } from "../types";

/** Citation numbers in order of first appearance across the answer's sentences. */
export function numberCitations(sentences: Sentence[]): Map<string, number> {
  const order = new Map<string, number>();
  for (const s of sentences) {
    for (const id of s.cited_ids) {
      if (!order.has(id)) order.set(id, order.size + 1);
    }
  }
  return order;
}

/** DOM id for an evidence card, used by Sources jump-to and the drawer. */
export function cardId(passageId: string): string {
  return `card-${passageId.replace(/[^a-z0-9]/gi, "-")}`;
}
