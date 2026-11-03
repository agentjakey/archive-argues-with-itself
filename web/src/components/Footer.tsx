import type { View } from "../lib/urlstate";

interface Props {
  onView?: (view: View) => void;
}

const LINKS: { view: View; label: string }[] = [
  { view: "about", label: "About" },
  { view: "privacy", label: "Privacy" },
  { view: "terms", label: "Terms of use" },
  { view: "accessibility", label: "Accessibility" },
  { view: "corrections", label: "Corrections and care" },
];

export function Footer({ onView }: Props) {
  return (
    <footer className="mt-12 border-t border-rule pt-4 text-sm text-muted">
      {onView && (
        <nav aria-label="About this site" className="mb-2 flex flex-wrap gap-x-4 gap-y-1">
          {LINKS.map((l) => (
            <a
              key={l.view}
              className="linkish"
              href={`?view=${l.view}`}
              onClick={(e) => {
                e.preventDefault();
                onView(l.view);
              }}
            >
              {l.label}
            </a>
          ))}
        </nav>
      )}
      <p>
        An independent project built during the 2026 AI Builders Fellowship with the BC + AI Ecosystem and
        Internet Archive Canada. Answers are written by an AI model and can be wrong.{" "}
        <a className="linkish" href="https://github.com/agentjakey/archive-argues-with-itself" target="_blank" rel="noopener noreferrer">
          Source on GitHub
        </a>
        , MIT. Page images are served by archive.org; the publications remain under their own terms.
      </p>
    </footer>
  );
}
