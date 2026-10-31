interface Props {
  detail: string;
  onRetry?: () => void;   // ask the same question again
}

/** The server's error detail, or a plain sentence for a refused check, in the same neutral card as
 *  everything else, with a way to try again. */
export function ErrorCard({ detail, onRetry }: Props) {
  return (
    <article className="card" role="status" aria-labelledby="error-heading">
      <h2 id="error-heading" className="font-sans text-sm uppercase tracking-wide text-muted">
        The request did not complete
      </h2>
      <p className="mt-3 max-w-prose leading-relaxed">{detail}</p>
      {onRetry && (
        <button type="button" className="chip chip-primary mt-3" onClick={onRetry}>
          Try again
        </button>
      )}
    </article>
  );
}
