// Gap Hunt: a grid of places by decade showing where the record goes quiet and why. Each state has
// its own pattern and word as well as its colour. It doubles as the attract loop: with no one at
// the screen it walks through the decades on its own (unless the visitor asked for less motion).
import { useEffect, useState } from "react";
import type { GapCell, GapHunt as Grid, Lang } from "../lib/deck";
import type { Strings } from "../lib/strings";
import { PLACE_NAMES } from "../lib/strings";

type Props = { grid: Grid; lang: Lang; t: Strings; attract?: boolean; reducedMotion: boolean; onStart?: () => void };

const STATE_ORDER = ["recorded", "not_indexed", "quiet_examined", "unknown"] as const;

function catalogueText(cell: GapCell, lang: Lang): string {
  if (cell.catalogue_items === null) return "?";
  return cell.catalogue_items.toLocaleString(lang === "fr" ? "fr-CA" : "en-CA");
}

export function GapHunt({ grid, lang, t, attract = false, reducedMotion, onStart }: Props) {
  const [picked, setPicked] = useState<GapCell | null>(null);
  const [tick, setTick] = useState(0);
  useEffect(() => {
    if (!attract || reducedMotion) return;
    const timer = window.setInterval(() => setTick((n) => n + 1), 4000);
    return () => window.clearInterval(timer);
  }, [attract, reducedMotion]);
  const names = PLACE_NAMES[lang];
  const spotlight = attract ? grid.cells.filter((c) => c.state !== "recorded")[tick % Math.max(1, grid.cells.filter((c) => c.state !== "recorded").length)] : null;
  const shown = picked ?? spotlight;
  const explain = (cell: GapCell) => {
    const place = names[cell.place] ?? cell.place;
    return t.gap.explain[cell.state](place, cell.decade, cell.indexed_items, catalogueText(cell, lang));
  };
  return (
    <section className={`mode gaphunt${attract ? " attract" : ""}`} aria-labelledby="gap-heading" onClick={attract ? onStart : undefined}>
      <h2 id="gap-heading">{t.gap.heading}</h2>
      {!attract && <p className="lede">{t.gap.intro}</p>}
      <div className="gap-grid-wrap">
        <table className="gap-grid">
          <caption className="sr-only">{t.gap.heading}</caption>
          <thead>
            <tr>
              <th scope="col">
                <span className="sr-only">{t.gap.legend}</span>
              </th>
              {grid.decades.map((d) => (
                <th key={d} scope="col">
                  {t.gap.decade(d)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {grid.jurisdictions.map((place) => (
              <tr key={place}>
                <th scope="row">{names[place] ?? place}</th>
                {grid.decades.map((d) => {
                  const cell = grid.cells.find((c) => c.place === place && c.decade === d);
                  if (!cell) return <td key={d} />;
                  const active = shown === cell;
                  return (
                    <td key={d}>
                      <button
                        type="button"
                        className={`cell cell-${cell.state}${active ? " cell-active" : ""}`}
                        aria-pressed={picked === cell}
                        aria-label={`${names[place] ?? place}, ${t.gap.decade(d)}: ${t.gap.states[cell.state]}`}
                        tabIndex={attract ? -1 : 0}
                        onClick={(e) => {
                          if (attract) return;
                          e.stopPropagation();
                          setPicked(cell);
                        }}
                      >
                        <span className="cell-count" aria-hidden="true">
                          {cell.indexed_items > 0 ? cell.indexed_items.toLocaleString(lang === "fr" ? "fr-CA" : "en-CA") : ""}
                        </span>
                      </button>
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <ul className="legend" aria-label={t.gap.legend}>
        {STATE_ORDER.map((s) => (
          <li key={s}>
            <span className={`cell cell-${s} legend-swatch`} aria-hidden="true" /> {t.gap.states[s]}
          </li>
        ))}
      </ul>
      <p className="gap-explain" aria-live="polite">
        {shown ? explain(shown) : ""}
      </p>
      {!attract && (
        <>
          {grid.catalogue && <p className="note">{t.gap.method(grid.catalogue.fetched_at.slice(0, 10), grid.catalogue.total)}</p>}
          <p className="note">{t.gap.unknownPlace(grid.unknown_place_indexed)}</p>
        </>
      )}
    </section>
  );
}
