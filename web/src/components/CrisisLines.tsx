import type { CrisisResource } from "../types";

interface Props {
  lines: CrisisResource[];
}

/** Calm, plain list of support resources, rendered exactly as provided by the single source of
 *  truth (src/archive_debugger/crisis.py) via the API. Each shows its label, how to reach it, who
 *  it is for, and its hours. Static, works offline. */
export function CrisisLines({ lines }: Props) {
  if (!lines || lines.length === 0) return null;
  return (
    <div className="mt-3">
      <p className="font-sans text-xs uppercase tracking-wide text-muted">If you need support</p>
      <ul className="mt-2 space-y-2">
        {lines.map((l) => (
          <li key={l.key} className="text-sm">
            <span className="font-semibold">{l.label}</span>: {l.contact}
            <div className="text-muted">For: {l["for"]}</div>
            <div className="text-muted">Hours: {l.hours}</div>
            {l.link ? <div className="text-muted">{l.link}</div> : null}
          </li>
        ))}
      </ul>
    </div>
  );
}
