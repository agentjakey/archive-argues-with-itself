interface Props {
  lanes: { key: string; count: number }[];
  onJump: (key: string) => void;
}

/** Sticky rail of decade lanes with counts; zero-hit lanes stay visible, greyed. */
export function DecadeRail({ lanes, onJump }: Props) {
  return (
    <nav className="sticky top-0 z-10 bg-paper/95 py-2 border-b border-rule" aria-label="Decades">
      <ul className="flex flex-wrap gap-2">
        {lanes.map((l) => (
          <li key={l.key}>
            <button
              type="button"
              className={`chip ${l.count === 0 ? "text-muted border-rule" : ""}`}
              aria-disabled={l.count === 0}
              onClick={() => onJump(l.key)}
            >
              {l.key} <span className="font-mono ml-1">({l.count})</span>
            </button>
          </li>
        ))}
      </ul>
    </nav>
  );
}
