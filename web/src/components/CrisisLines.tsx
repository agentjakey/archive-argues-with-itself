import type { Flagged } from "../types";

interface Props {
  lines: Flagged["crisis_lines"];
}

/** Calm, plain list of support lines. Numbers render exactly as provided (the 9-8-8 entry
 *  carries its "call or text" instruction in the number field). Static, works offline. */
export function CrisisLines({ lines }: Props) {
  if (!lines || lines.length === 0) return null;
  return (
    <div className="mt-3">
      <p className="font-sans text-xs uppercase tracking-wide text-muted">If you need support</p>
      <ul className="mt-1 space-y-1">
        {lines.map((l) => (
          <li key={`${l.name}|${l.number}`} className="text-sm">
            {l.name}: <span className="font-semibold">{l.number}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
