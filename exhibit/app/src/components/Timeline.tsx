// The When Was This? reveal on one line of years: the guess above the line (a triangle), the year
// the page was published below it (a square), and the gap between them shaded. The same facts are
// in the words beside it, and in the label a screen reader reads.
type Props = { guess: number; actual: number; first: number; last: number; youLabel: string; publishedLabel: string; label: string };

export function Timeline({ guess, actual, first, last, youLabel, publishedLabel, label }: Props) {
  const span = Math.max(1, last - first);
  const share = (y: number) => ((Math.min(last, Math.max(first, y)) - first) / span) * 100;
  const decades: number[] = [];
  for (let d = Math.ceil(first / 10) * 10; d <= last; d += 10) decades.push(d);
  const lo = share(Math.min(guess, actual));
  const hi = share(Math.max(guess, actual));
  return (
    <div className="timeline" role="img" aria-label={label}>
      <span className="timeline-end">{first}</span>
      <div className="timeline-track" aria-hidden="true">
        <span className="timeline-line" />
        <span className="timeline-gap" style={{ left: `${lo}%`, width: `${hi - lo}%` }} />
        {decades.map((d) => (
          <span key={d} className="timeline-decade" style={{ left: `${share(d)}%` }} />
        ))}
        <span className="timeline-mark timeline-guess" style={{ left: `${share(guess)}%` }}>
          <span className="timeline-tag">
            {youLabel} {guess}
          </span>
          <svg viewBox="0 0 20 20" className="timeline-glyph" focusable="false">
            <polygon points="2,3 18,3 10,18" />
          </svg>
        </span>
        <span className="timeline-mark timeline-actual" style={{ left: `${share(actual)}%` }}>
          <svg viewBox="0 0 20 20" className="timeline-glyph" focusable="false">
            <rect x="3" y="3" width="14" height="14" />
          </svg>
          <span className="timeline-tag">
            {publishedLabel} {actual}
          </span>
        </span>
      </div>
      <span className="timeline-end">{last}</span>
    </div>
  );
}
