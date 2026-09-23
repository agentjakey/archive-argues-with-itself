import { useEffect, useMemo, useState } from "react";
import { formatInt } from "../lib/format";
import { BANDS, PROVINCES, bandOf, countsByJurisdiction, provinceByCode } from "../lib/coverage";
import { featurePath, fitConicConformal, isFeatureCollection, type FeatureCollection } from "../lib/canadaMap";
import type { View } from "../lib/urlstate";
import type { ScopeInfo } from "../types";
import { Page } from "./pages/Page";

const MAP_W = 720;
const MAP_H = 460;

// Author-fixed caption for the national map (verbatim). About 15% is the microlog proxy-unknown share.
const CAPTION =
  "Jurisdiction here is a rough proxy. About 15% of items could not be placed and are not shown on " +
  "the map. This is a rough picture of reach, not a scorecard.";

interface Props {
  scope: ScopeInfo | null;
  onExplore: (slug: string) => void;
  onNav: (view: View) => void;
}

/** Coverage map: a real, recognizable map of Canada (Lambert conic, rendered from a LOCAL boundary
 *  file, no external tiles or basemap fetch) shaded in coarse bands. Jurisdiction is an issuer-derived
 *  proxy with ~15% unknown, so this is orientation, not a scorecard: no exact counts as fact, the
 *  unknown items shown as a separate figure, and the pilot (federal + Ontario + Alberta) never drawn as
 *  a national ranking. Keyboard-navigable, ARIA-labelled, with a text-alternative table that carries
 *  the same figures; when web/public/canada.geojson is absent, it falls back to that table cleanly. */
export function CoverageMap({ scope, onExplore, onNav }: Props) {
  const [geo, setGeo] = useState<FeatureCollection | null>(null);
  useEffect(() => {
    let alive = true;
    const url = `${import.meta.env.BASE_URL || "/"}canada.geojson`;
    fetch(url)
      .then((r) => (r.ok ? r.json() : null))
      .then((j) => { if (alive) setGeo(isFeatureCollection(j) ? j : null); })
      .catch(() => { if (alive) setGeo(null); });   // absent boundary file -> the text alternative, no error
    return () => { alive = false; };
  }, []);
  return (
    <Page title="Coverage map">
      <p>
        A rough map of where this record reaches across Canada
        {scope ? <> (<span className="text-ink">{scope.label}</span>)</> : null}. Jurisdiction is an
        issuer-derived proxy, so this is orientation, not a scorecard: provinces are shaded in coarse
        bands, exact counts are never claimed as precise, and the items with no jurisdiction signal are
        shown as a separate figure, never spread across provinces.
      </p>
      {!scope?.composition ? (
        <p className="text-muted" aria-live="polite">Loading coverage.</p>
      ) : (
        <CoverageMapView scope={scope} geo={geo} onExplore={onExplore} onNav={onNav} />
      )}
    </Page>
  );
}

export function CoverageMapView({
  scope, geo, onExplore, onNav,
}: {
  scope: ScopeInfo;
  geo: FeatureCollection | null;
  onExplore: (s: string) => void;
  onNav: (v: View) => void;
}) {
  const comp = scope.composition!;
  const counts = countsByJurisdiction(comp.jurisdictions);
  const isFloor = comp.jurisdiction_is_floor;
  const federal = counts["federal"] ?? 0;
  const international = counts["international"] ?? 0;
  const unknown = counts["unknown"] ?? 0;
  const unknownPct = Math.round(comp.jurisdiction_unknown_share * 100);
  const national = scope.name !== "pilot";   // the pilot (federal + Ontario + Alberta) is not national
  const [active, setActive] = useState<string | null>(null);

  const rows = useMemo(() => PROVINCES.map((p) => ({ ...p, count: counts[p.slug] ?? 0 })), [counts]);
  const placedTotal = rows.reduce((n, p) => n + p.count, 0);

  const shareText = (count: number): string =>
    count <= 0
      ? "not placed in this corpus"
      : `roughly ${placedTotal ? Math.max(1, Math.round((count / placedTotal) * 100)) : 0}% of placed items (rough proxy)`;

  const bandLabel = (count: number): string =>
    national ? bandOf(count)?.label ?? "not placed" : count > 0 ? "in this pilot" : "not in this pilot";

  const project = useMemo(
    () => (geo && geo.features.length ? fitConicConformal(geo.features, MAP_W, MAP_H) : null),
    [geo],
  );
  const activeRow = active ? rows.find((p) => p.slug === active) ?? null : null;

  return (
    <>
      {!national && (
        <p className="mt-3 rounded border border-rule bg-sheet px-3 py-2 text-sm">
          This pilot covers <span className="text-ink">federal, Ontario, and Alberta</span> only. It is
          not a national picture, so there is no national ranking here: Ontario and Alberta are
          highlighted, federal is stated separately below, and the rest of the map is shown de-emphasized
          for orientation.
        </p>
      )}

      <figure className="mt-4 m-0">
        {project && geo ? (
          <svg
            viewBox={`0 0 ${MAP_W} ${MAP_H}`}
            className="w-full h-auto max-w-[760px]"
            role="group"
            aria-label={`A map of Canada showing where ${scope.label} reaches, shaded in coarse proxy bands, not a precise scorecard.`}
          >
            <defs>
              <pattern id="cov-none" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
                <rect width="6" height="6" fill="#fcfaf4" />
                <line x1="0" y1="0" x2="0" y2="6" stroke="#d9d2c3" strokeWidth="2" />
              </pattern>
              <style>{".cov-p:focus{outline:none}.cov-p:hover,.cov-p:focus{stroke:#8b2e1f;stroke-width:2}.cov-click{cursor:pointer}"}</style>
            </defs>
            {geo.features.map((f, i) => {
              const d = featurePath(f, project);
              if (!d) return null;
              const prov = provinceByCode(f.properties?.code as string | undefined);
              const count = prov ? counts[prov.slug] ?? 0 : 0;
              const isONAB = !!prov && (prov.slug === "ontario" || prov.slug === "alberta");
              let fill = "url(#cov-none)";
              if (national) fill = bandOf(count)?.fill ?? "url(#cov-none)";
              else fill = isONAB && count > 0 ? "#8a6a3f" : "#f2ecdd";   // pilot: highlight ON/AB, rest de-emphasized
              const explorable = !!prov && count > 0 && (national || isONAB);
              const label = prov
                ? `${prov.name}: ${bandLabel(count)}, ${shareText(count)}`
                : "area outside the corpus jurisdictions";
              return (
                <path
                  key={(f.properties?.code as string) ?? i}
                  d={d}
                  fill={fill}
                  stroke="#b8ad97"
                  strokeWidth={0.8}
                  className={`cov-p ${explorable ? "cov-click" : ""}`}
                  tabIndex={prov ? 0 : -1}
                  role={explorable ? "button" : "img"}
                  aria-label={label}
                  onMouseEnter={() => prov && setActive(prov.slug)}
                  onMouseLeave={() => setActive(null)}
                  onFocus={() => prov && setActive(prov.slug)}
                  onBlur={() => setActive(null)}
                  onClick={explorable ? () => onExplore(prov!.slug) : undefined}
                  onKeyDown={
                    explorable
                      ? (e) => {
                          if (e.key === "Enter" || e.key === " ") {
                            e.preventDefault();
                            onExplore(prov!.slug);
                          }
                        }
                      : undefined
                  }
                >
                  <title>{label}</title>
                </path>
              );
            })}
          </svg>
        ) : (
          <p className="text-sm text-muted">
            The map image is not on this device. The same figures are in the list below.
          </p>
        )}

        <p className="mt-2 min-h-[1.5em] text-sm" aria-live="polite">
          {activeRow ? (
            <span>
              <span className="text-ink">{activeRow.name}</span>
              {" -- "}
              {bandLabel(activeRow.count)}, {shareText(activeRow.count)}
            </span>
          ) : (
            <span className="text-muted">Hover or tab a province for its band and approximate share.</span>
          )}
        </p>

        <figcaption className="mt-2 max-w-prose text-sm text-muted">
          {national ? CAPTION : "This pilot is federal, Ontario, and Alberta only, not a national map."}
        </figcaption>

        <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-2 text-sm" aria-hidden="true">
          {national ? (
            <>
              {BANDS.map((b) => (
                <span key={b.key} className="inline-flex items-center gap-2">
                  <span style={{ background: b.fill }} className="inline-block h-4 w-4 border border-rule" />
                  {b.label}
                </span>
              ))}
              <span className="inline-flex items-center gap-2">
                <span style={{ backgroundImage: "repeating-linear-gradient(45deg,#fcfaf4,#fcfaf4 2px,#d9d2c3 2px,#d9d2c3 4px)" }} className="inline-block h-4 w-4 border border-rule" />
                not placed
              </span>
            </>
          ) : (
            <>
              <span className="inline-flex items-center gap-2">
                <span style={{ background: "#8a6a3f" }} className="inline-block h-4 w-4 border border-rule" />
                in this pilot (Ontario, Alberta)
              </span>
              <span className="inline-flex items-center gap-2">
                <span style={{ background: "#f2ecdd" }} className="inline-block h-4 w-4 border border-rule" />
                not in this pilot
              </span>
            </>
          )}
        </div>
      </figure>

      <div className="mt-5 border-t border-rule pt-3">
        <h3 className="tag">Not shown on the map</h3>
        <ul className="mt-1 space-y-1 text-sm">
          <li>
            <span className="text-ink">About {unknownPct}% of items ({formatInt(unknown)})</span> could not
            be placed and are not shown on the map. They are counted here, never spread across provinces.
          </li>
          <li>
            <span className="text-ink">Federal (national): {formatInt(federal)} items</span> -- a
            national issuer, not a province.
          </li>
          {international > 0 && <li>International: {formatInt(international)} items.</li>}
        </ul>
      </div>

      {isFloor && (
        <p className="mt-3 max-w-prose text-sm text-muted">
          These bands are proxy-derived and a floor, not precise per-province coverage: an item is placed
          only when its issuer metadata names the jurisdiction, so a body that does not name its province
          stays in the unknown figure rather than being guessed onto the map.
        </p>
      )}

      <div className="mt-5 border-t border-rule pt-3">
        <h3 className="tag">The same figures as a list</h3>
        <table className="mt-2 text-sm">
          <caption className="sr-only">Coverage band by province or territory for {scope.label}. Jurisdiction is a rough proxy.</caption>
          <thead>
            <tr>
              <th scope="col" className="pr-6 text-left font-sans font-semibold">Province or territory</th>
              <th scope="col" className="pr-6 text-left font-sans font-semibold">{national ? "Band" : "In this pilot"}</th>
              <th scope="col" className="text-left font-sans font-semibold">Approx. share (proxy)</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((p) => (
              <tr key={p.slug}>
                <td className="pr-6">{p.name}</td>
                <td className="pr-6">{national ? bandLabel(p.count) : p.count > 0 ? "yes" : "no"}</td>
                <td className="text-muted">{shareText(p.count)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <p className="mt-5 border-t border-rule pt-3 text-sm text-muted">
        This is a rough picture of reach, not a scorecard. See{" "}
        <button type="button" className="linkish" onClick={() => onNav("gaps")}>Gaps</button>{" "}
        for what is missing and{" "}
        <button type="button" className="linkish" onClick={() => onNav("how")}>How this works</button>{" "}
        for how jurisdiction is derived.
      </p>
    </>
  );
}
