import type { ReactNode } from "react";

/** Reading-room page: serif headings, one column of prose, rules not boxes. The main is the single
 *  landmark for the view and the skip-link / focus target (id main-content); the heading is made
 *  programmatically focusable (tabIndex -1) so a page change moves focus to it. */
export function Page({ title, children }: { title: string; children: ReactNode }) {
  return (
    <main id="main-content" tabIndex={-1} className="reading" aria-labelledby="page-heading">
      <h2 id="page-heading" tabIndex={-1} className="font-serif text-2xl">
        {title}
      </h2>
      <div className="mt-3 max-w-prose leading-relaxed reading-body">{children}</div>
    </main>
  );
}

/** Small citation of the repository file a number was copied from. */
export function Source({ file }: { file: string }) {
  return (
    <span className="tag" title="Source file in the repository">
      {file}
    </span>
  );
}
