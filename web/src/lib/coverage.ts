// Layout and color bins for the coverage map (a tile-grid choropleth of Canada). Equal-area
// tiles, arranged roughly west-to-east with the territories on top, so the map never distorts
// coverage by land area and never implies national uniformity. Every tile also shows its count,
// so the map is readable without color (colorblind- and print-safe). No-data is a hatch, never a
// ramp step, so absence never reads as a little coverage.

export interface Tile {
  slug: string;   // jurisdiction_norm value the resolver produces
  abbr: string;
  name: string;
  col: number;
  row: number;
}

// 7 columns (0..6 west->east), 3 rows (0 north). Atlantic clusters at the northeast corner.
export const PROVINCE_TILES: Tile[] = [
  { slug: "yukon", abbr: "YT", name: "Yukon", col: 1, row: 0 },
  { slug: "northwest_territories", abbr: "NT", name: "Northwest Territories", col: 2, row: 0 },
  { slug: "nunavut", abbr: "NU", name: "Nunavut", col: 3, row: 0 },
  { slug: "newfoundland", abbr: "NL", name: "Newfoundland and Labrador", col: 6, row: 0 },
  { slug: "british_columbia", abbr: "BC", name: "British Columbia", col: 0, row: 1 },
  { slug: "alberta", abbr: "AB", name: "Alberta", col: 1, row: 1 },
  { slug: "saskatchewan", abbr: "SK", name: "Saskatchewan", col: 2, row: 1 },
  { slug: "manitoba", abbr: "MB", name: "Manitoba", col: 3, row: 1 },
  { slug: "ontario", abbr: "ON", name: "Ontario", col: 4, row: 1 },
  { slug: "quebec", abbr: "QC", name: "Quebec", col: 5, row: 1 },
  { slug: "prince_edward_island", abbr: "PE", name: "Prince Edward Island", col: 6, row: 1 },
  { slug: "new_brunswick", abbr: "NB", name: "New Brunswick", col: 5, row: 2 },
  { slug: "nova_scotia", abbr: "NS", name: "Nova Scotia", col: 6, row: 2 },
];

// Every province/territory the resolver can produce; used for the floor caveat check.
export const PROVINCE_SLUGS = new Set(PROVINCE_TILES.map((t) => t.slug));

// Buckets shown off the map, not as province tiles (federal is national; unknown has no province).
export const OFFMAP_SLUGS = ["federal", "international", "unknown"] as const;

// Single-hue warm sequential ramp (light -> dark), harmonized with the paper/ink tokens. Fixed
// count thresholds (not per-scope quantiles) so the same count reads the same across scopes.
export interface Bucket {
  min: number;
  label: string;
  fill: string;
  text: string;
}

export const BUCKETS: Bucket[] = [
  { min: 600, label: "600 or more", fill: "#4a3a24", text: "#f6f1e7" },
  { min: 300, label: "300 to 599", fill: "#8a6a3f", text: "#f6f1e7" },
  { min: 100, label: "100 to 299", fill: "#c2a273", text: "#1c1a17" },
  { min: 1, label: "1 to 99", fill: "#e3d7bd", text: "#1c1a17" },
];

/** The color bucket for an item count, or null for no data (absent or zero). No data is never a
 *  ramp step: the caller renders it as a hatch. */
export function bucketOf(count: number): Bucket | null {
  if (!count || count <= 0) return null;
  for (const b of BUCKETS) {
    if (count >= b.min) return b;
  }
  return BUCKETS[BUCKETS.length - 1];
}

/** name -> item count, from a scope composition's jurisdiction list. */
export function countsByJurisdiction(jurisdictions: { name: string; items: number }[]): Record<string, number> {
  const out: Record<string, number> = {};
  for (const j of jurisdictions) out[j.name] = j.items;
  return out;
}
