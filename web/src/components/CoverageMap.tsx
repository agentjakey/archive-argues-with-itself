import { formatInt } from "../lib/format";
import { BUCKETS, PROVINCE_TILES, bucketOf, countsByJurisdiction } from "../lib/coverage";
import type { View } from "../lib/urlstate";
import type { ScopeInfo } from "../types";
import { Page } from "./pages/Page";

const CELL = 84;
const PAD = 4;
const SIZE = CELL - PAD * 2;
const COLS = 7;
const ROWS = 3;

interface Props {
  scope: ScopeInfo | null;
  onExplore: (slug: string) => void;
  onNav: (view: View) => void;
}

/** Coverage map: a tile-grid choropleth of the active scope's per-province/territory item
 *  density, from the live /scopes composition (never hardcoded). No-data is a hatch, distinct
 *  from the low end; the unknown and federal counts sit off the map; a resolved tile is
 *  clickable and carries the floor caveat downstream. */
export function CoverageMap({ scope, onExplore, onNav }: Props) {
  const comp = scope?.composition;
  return (
    <Page title="Coverage map">
      <p>
        Where the record is thick and thin across Canada for the corpus you are exploring
        {scope ? <> (<span className="text-ink">{scope.label}</span>)</> : null}. Each tile is a
        province or territory, shaded by how many items name it as their jurisdiction. Colour is
        real item count, not land area, and no-data is hatched, not a pale colour, so an empty
        jurisdiction never reads as a little coverage.
      </p>
      {!comp ? (
        <p className="text-muted" aria-live="polite">
          Loading coverage.
        </p>
      ) : (
        <CoverageBody scope={scope!} onExplore={onExplore} onNav={onNav} />
      )}
    </Page>
  );
}

function CoverageBody({ scope, onExplore, onNav }: { scope: ScopeInfo; onExplore: (s: string) => void; onNav: (v: View) => void }) {
  const comp = scope.composition!;
  const counts = countsByJurisdiction(comp.jurisdictions);
  const isFloor = comp.jurisdiction_is_floor;
  const federal = counts["federal"] ?? 0;
  const unknown = counts["unknown"] ?? 0;
  const international = counts["international"] ?? 0;
  const unknownPct = Math.round(comp.jurisdiction_unknown_share * 100);

  return (
    <>
      <figure className="mt-4 m-0">
        <svg
          viewBox={`0 0 ${COLS * CELL} ${ROWS * CELL}`}
          className="w-full max-w-[620px] h-auto"
          role="group"
          aria-label={`Coverage of ${scope.label} by province and territory`}
        >
          <defs>
            <pattern id="cov-nodata" width="7" height="7" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
              <rect width="7" height="7" fill="#fcfaf4" />
              <line x1="0" y1="0" x2="0" y2="7" stroke="#d9d2c3" strokeWidth="2.5" />
            </pattern>
            <style>{".cov-clickable{cursor:pointer}.cov-clickable:hover rect,.cov-clickable:focus rect{stroke:#8b2e1f;stroke-width:3}"}</style>
          </defs>
          {PROVINCE_TILES.map((t) => {
            const count = counts[t.slug] ?? 0;
            const bucket = bucketOf(count);
            const x = t.col * CELL + PAD;
            const y = t.row * CELL + PAD;
            const resolved = count > 0;
            const fill = bucket ? bucket.fill : "url(#cov-nodata)";
            const textColor = bucket ? bucket.text : "#6b655c";
            const label = resolved
              ? `${t.name}: ${formatInt(count)} items${isFloor ? " (proxy floor)" : ""}`
              : `${t.name}: no data`;
            return (
              <g
                key={t.slug}
                aria-label={label}
                role={resolved ? "button" : undefined}
                tabIndex={resolved ? 0 : undefined}
                className={resolved ? "cov-clickable" : undefined}
                onClick={resolved ? () => onExplore(t.slug) : undefined}
                onKeyDown={
                  resolved
                    ? (e) => {
                        if (e.key === "Enter" || e.key === " ") {
                          e.preventDefault();
                          onExplore(t.slug);
                        }
                      }
                    : undefined
                }
              >
                <title>{label}</title>
                <rect x={x} y={y} width={SIZE} height={SIZE} fill={fill} stroke="#d9d2c3" strokeWidth="1.5" rx="3" />
                <text x={x + SIZE / 2} y={y + SIZE / 2 - 6} textAnchor="middle" fontSize="20" fontWeight="600" fill={textColor} fontFamily="ui-sans-serif, system-ui">
                  {t.abbr}
                </text>
                <text x={x + SIZE / 2} y={y + SIZE / 2 + 18} textAnchor="middle" fontSize="14" fill={textColor} fontFamily="ui-monospace, monospace">
                  {resolved ? formatInt(count) : "no data"}
                </text>
              </g>
            );
          })}
        </svg>
        <figcaption className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-2 text-sm">
          {[...BUCKETS].reverse().map((b) => (
            <span key={b.label} className="inline-flex items-center gap-2">
              <span aria-hidden="true" style={{ background: b.fill }} className="inline-block h-4 w-4 border border-rule" />
              {b.label}
            </span>
          ))}
          <span className="inline-flex items-center gap-2">
            <span aria-hidden="true" style={{ backgroundImage: "repeating-linear-gradient(45deg,#fcfaf4,#fcfaf4 2px,#d9d2c3 2px,#d9d2c3 4px)" }} className="inline-block h-4 w-4 border border-rule" />
            no data
          </span>
        </figcaption>
      </figure>

      <div className="mt-5 border-t border-rule pt-3">
        <h3 className="tag">Not on the map</h3>
        <p className="mt-1 text-sm">
          These items are real but sit on no province or territory tile:{" "}
          <span className="text-ink">federal {formatInt(federal)}</span> items
          {international > 0 ? <>, international {formatInt(international)} items</> : null}, and{" "}
          <span className="text-ink">{formatInt(unknown)}</span> items ({unknownPct}%) with no
          jurisdiction signal in their issuer metadata (unknown). The map does not fold these into any
          province.
        </p>
      </div>

      {isFloor && (
        <p className="mt-3 text-sm text-muted">
          These per-province counts are proxy-derived and a floor, not precise per-province coverage:
          an item is placed only when its issuer metadata names the jurisdiction, so a body that does
          not name its province stays in the unknown count rather than being guessed onto the map.
        </p>
      )}

      <p className="mt-5 border-t border-rule pt-3 text-sm text-muted">
        Coverage is uneven: the record is thick in a few jurisdictions and thin or absent in most. It
        was never national and this map does not pretend otherwise. See{" "}
        <button type="button" className="linkish" onClick={() => onNav("gaps")}>
          Gaps
        </button>{" "}
        for what is missing and{" "}
        <button type="button" className="linkish" onClick={() => onNav("how")}>
          How this works
        </button>{" "}
        for how jurisdiction is derived.
      </p>
    </>
  );
}
