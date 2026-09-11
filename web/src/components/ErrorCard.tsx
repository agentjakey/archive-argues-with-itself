interface Props {
  detail: string;
}

/** The server's error detail, verbatim, in the same neutral card as everything else. */
export function ErrorCard({ detail }: Props) {
  return (
    <article className="card" role="status" aria-labelledby="error-heading">
      <h2 id="error-heading" className="font-sans text-sm uppercase tracking-wide text-muted">
        The request did not complete
      </h2>
      <p className="mt-3 max-w-prose leading-relaxed">{detail}</p>
    </article>
  );
}
