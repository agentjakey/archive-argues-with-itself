// Province/territory metadata and the coarse coverage bands for the coverage map. The map is a real
// map of Canada (see canadaMap.ts + CoverageMap.tsx), shaded in three coarse bands, NOT a precise
// per-province scorecard: jurisdiction is an issuer-derived proxy with ~15% unknown, so exact counts
// are never presented as fact. A single-hue light->dark ramp keeps the bands colorblind- and print-safe.

export interface Province {
  slug: string;   // jurisdiction_norm value the resolver produces
  abbr: string;   // postal code; the ISO 3166-2 code is "CA-" + abbr, which matches the geojson features
  name: string;
}

export const PROVINCES: Province[] = [
  { slug: "british_columbia", abbr: "BC", name: "British Columbia" },
  { slug: "alberta", abbr: "AB", name: "Alberta" },
  { slug: "saskatchewan", abbr: "SK", name: "Saskatchewan" },
  { slug: "manitoba", abbr: "MB", name: "Manitoba" },
  { slug: "ontario", abbr: "ON", name: "Ontario" },
  { slug: "quebec", abbr: "QC", name: "Quebec" },
  { slug: "new_brunswick", abbr: "NB", name: "New Brunswick" },
  { slug: "nova_scotia", abbr: "NS", name: "Nova Scotia" },
  { slug: "prince_edward_island", abbr: "PE", name: "Prince Edward Island" },
  { slug: "newfoundland", abbr: "NL", name: "Newfoundland and Labrador" },
  { slug: "yukon", abbr: "YT", name: "Yukon" },
  { slug: "northwest_territories", abbr: "NT", name: "Northwest Territories" },
  { slug: "nunavut", abbr: "NU", name: "Nunavut" },
];

export const PROVINCE_SLUGS = new Set(PROVINCES.map((p) => p.slug));

/** A geojson feature's ISO 3166-2 code (e.g. "CA-ON") -> our province, or undefined. */
export function provinceByCode(code: string | undefined): Province | undefined {
  if (!code) return undefined;
  const abbr = (code.startsWith("CA-") ? code.slice(3) : code).toUpperCase();
  return PROVINCES.find((p) => p.abbr === abbr);
}

/** name -> item count, from a scope composition's jurisdiction list. */
export function countsByJurisdiction(jurisdictions: { name: string; items: number }[]): Record<string, number> {
  const out: Record<string, number> = {};
  for (const j of jurisdictions) out[j.name] = j.items;
  return out;
}

// Three coarse bands on a single-hue light->dark ramp (colorblind- and print-safe). Fixed count
// thresholds so the same amount reads the same across scopes; labelled with words, never exact counts,
// because jurisdiction is a proxy and the map is reach, not a ranking.
export interface Band {
  key: "well" | "some" | "sparse";
  label: string;
  fill: string;
  text: string;
}

export const BANDS: Band[] = [
  { key: "well", label: "well represented", fill: "#7a5a30", text: "#f6f1e7" },
  { key: "some", label: "some", fill: "#c2a273", text: "#1c1a17" },
  { key: "sparse", label: "sparse", fill: "#e6dcc6", text: "#1c1a17" },
];

/** The coarse band for a province's item count, or null for none (absent / zero). Thresholds are
 *  deliberately coarse; the map never presents the exact count as a precise fact. */
export function bandOf(count: number): Band | null {
  if (!count || count <= 0) return null;
  if (count >= 300) return BANDS[0];
  if (count >= 50) return BANDS[1];
  return BANDS[2];
}
