// Minimal Lambert conformal conic projection + geojson path builder, so the coverage map renders a
// real, recognizable Canada from a LOCAL boundary file with no external dependency and no network
// (N1). Shape-equivalent to d3.geoConicConformal().fitSize(); if d3-geo is ever added, swap these two
// helpers for it. Standard parallels 49N and 77N, central meridian 96W -- a conventional Canada conic.

export interface Feature {
  type: "Feature";
  properties: { code?: string; [k: string]: unknown } | null;
  geometry: { type: "Polygon" | "MultiPolygon"; coordinates: number[][][] | number[][][][] } | null;
}

export interface FeatureCollection {
  type: "FeatureCollection";
  features: Feature[];
}

export function isFeatureCollection(x: unknown): x is FeatureCollection {
  return (
    !!x && typeof x === "object" &&
    (x as { type?: unknown }).type === "FeatureCollection" &&
    Array.isArray((x as { features?: unknown }).features)
  );
}

export type Projector = (lonlat: [number, number]) => [number, number];

const D = Math.PI / 180;

function rawConic(phi1 = 49, phi2 = 77, phi0 = 49, lon0 = -96): (lon: number, lat: number) => [number, number] {
  const p1 = phi1 * D, p2 = phi2 * D, p0 = phi0 * D, l0 = lon0 * D;
  const n = Math.log(Math.cos(p1) / Math.cos(p2)) / Math.log(Math.tan(Math.PI / 4 + p2 / 2) / Math.tan(Math.PI / 4 + p1 / 2));
  const f = (Math.cos(p1) * Math.pow(Math.tan(Math.PI / 4 + p1 / 2), n)) / n;
  const rho0 = f / Math.pow(Math.tan(Math.PI / 4 + p0 / 2), n);
  return (lon, lat) => {
    const g = lon * D, l = lat * D;
    const rho = f / Math.pow(Math.tan(Math.PI / 4 + l / 2), n);
    return [rho * Math.sin(n * (g - l0)), rho0 - rho * Math.cos(n * (g - l0))];
  };
}

function polygons(feature: Feature): number[][][][] {
  const geom = feature.geometry;
  if (!geom) return [];
  return geom.type === "Polygon" ? [geom.coordinates as number[][][]] : (geom.coordinates as number[][][][]);
}

/** Fit the conic projection to the features' bounds inside width x height (SVG y-down, north up). */
export function fitConicConformal(features: Feature[], width: number, height: number, pad = 6): Projector {
  const raw = rawConic();
  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
  for (const feat of features) {
    for (const poly of polygons(feat)) {
      for (const ring of poly) {
        for (const [lon, lat] of ring as [number, number][]) {
          const [x, y] = raw(lon, lat);
          if (x < minX) minX = x;
          if (x > maxX) maxX = x;
          if (y < minY) minY = y;
          if (y > maxY) maxY = y;
        }
      }
    }
  }
  if (!Number.isFinite(minX)) return ([, ]) => [width / 2, height / 2];
  const w = width - 2 * pad, h = height - 2 * pad;
  const dx = maxX - minX || 1, dy = maxY - minY || 1;
  const s = Math.min(w / dx, h / dy);
  const ox = pad + (w - s * dx) / 2, oy = pad + (h - s * dy) / 2;
  return ([lon, lat]) => {
    const [x, y] = raw(lon, lat);
    return [ox + s * (x - minX), oy + s * (maxY - y)];   // flip y for SVG
  };
}

/** SVG path 'd' for a feature (Polygon/MultiPolygon), projected. Empty for null geometry. */
export function featurePath(feature: Feature, project: Projector): string {
  let d = "";
  for (const poly of polygons(feature)) {
    for (const ring of poly) {
      (ring as [number, number][]).forEach((pt, i) => {
        const [x, y] = project(pt);
        d += `${i ? "L" : "M"}${x.toFixed(1)} ${y.toFixed(1)}`;
      });
      d += "Z";
    }
  }
  return d;
}
