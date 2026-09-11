import type { Unsupported } from "../types";

interface Props {
  items: Unsupported[];
}

/** Collapsed by default: "N claims not shown", each with the verifier's reason. */
export function UnsupportedRow({ items }: Props) {
  if (!items.length) return null;
  return (
    <details className="mt-4 border-t border-rule pt-3 text-sm">
      <summary className="cursor-pointer text-muted min-h-[44px] flex items-center">
        {items.length} {items.length === 1 ? "claim" : "claims"} not shown
      </summary>
      <ul className="mt-2 space-y-3">
        {items.map((u, i) => (
          <li key={i}>
            <p className="excerpt text-ink">{u.text}</p>
            <p className="text-muted mt-1">
              Reason: {u.reason}
              {u.cited_ids.length > 0 && (
                <>
                  {" "}
                  <span className="font-mono text-xs">[{u.cited_ids.join(", ")}]</span>
                </>
              )}
            </p>
          </li>
        ))}
      </ul>
    </details>
  );
}
