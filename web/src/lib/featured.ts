// The example questions offered beside the search box. Each is a seed question of its corpus with a
// recorded answer that answers it (not a refusal), cites at least two verified pages with page images,
// and carries no care flag; tests/featured.test.ts checks every one against site/data. Questions that
// lead to records the care rules keep out of demos (harm-related records, pages with period terms now
// offensive) are left out on purpose, even when the engine answers them well. A question shows only
// when its corpus's examples still list it, so a changed seed set drops it instead of breaking it.
import type { Example } from "../types";

export interface Featured {
  qid: string;
  topic: string;     // the short label on a chip: a topic, not a claim about what the record says
}

export const FEATURED: Record<string, Featured[]> = {
  pilot: [
    { qid: "q016", topic: "Drug safety" },
    { qid: "q006", topic: "SARS and hospitals" },
    { qid: "q019", topic: "Municipal sanitation" },
    { qid: "q027", topic: "Physical fitness" },
    { qid: "q001", topic: "Tobacco in Ontario" },
    { qid: "q020", topic: "Disease surveillance" },
  ],
  microlog: [
    { qid: "mq10", topic: "Drinking water" },
    { qid: "mq22", topic: "Tobacco control" },
    { qid: "mq40", topic: "SARS, 2003" },
    { qid: "mq13", topic: "Cancer registries" },
    { qid: "mq02", topic: "Notifiable diseases" },
  ],
};

export interface FeaturedQuestion extends Example {
  topic: string;
}

/** The featured questions of a corpus that its examples still list, in the order above. */
export function featuredFor(scope: string, examples: Example[]): FeaturedQuestion[] {
  const byQid = new Map(examples.map((e) => [e.qid, e]));
  return (FEATURED[scope] ?? [])
    .map((f) => {
      const e = byQid.get(f.qid);
      return e && e.gold !== "abstain" ? { ...e, topic: f.topic } : null;
    })
    .filter((e): e is FeaturedQuestion => e !== null);
}
