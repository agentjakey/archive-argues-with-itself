import type { ReactNode } from "react";

/** Reading-room page: serif headings, one column of prose, rules not boxes. The main is the single
 *  landmark for the view and the skip-link / focus target (id main-content); the heading is made
 *  programmatically focusable (tabIndex -1) so a page change moves focus to it. */
export function Page({ title, children, className }: { title: string; children: ReactNode; className?: string }) {
  return (
    <main id="main-content" tabIndex={-1} className={className ? `reading ${className}` : "reading"} aria-labelledby="page-heading">
      <h2 id="page-heading" tabIndex={-1} className="screen-title">
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

/** The date a public policy page last changed. Changes are logged in CHANGELOG.md. */
export function LastUpdated({ date }: { date: string }) {
  return (
    <p className="text-sm text-muted">
      Last updated <time dateTime={date}>{date}</time>.
    </p>
  );
}

/** A link that opens outside the site. */
export function Ext({ href, children }: { href: string; children: ReactNode }) {
  return (
    <a className="linkish" href={href} target="_blank" rel="noopener noreferrer">
      {children}
    </a>
  );
}

export const REPO_URL = "https://github.com/agentjakey/archive-argues-with-itself";
export const HELLO = "hello@archiveargues.org";
export const POLICY_DATE = "2026-10-31";
export const PRIVACY_DATE = "2026-11-01";
