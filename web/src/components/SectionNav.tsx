import type { View } from "../lib/urlstate";
import { sectionOf } from "./Header";

interface Props {
  view: View | null;
  onView: (view: View) => void;
}

const EXPLORE: { view: View | "catalogue"; label: string }[] = [
  { view: "explore", label: "Collections" },
  { view: "timeline", label: "Through time" },
  { view: "map", label: "Across Canada" },
  { view: "sources", label: "Sources" },
  { view: "catalogue", label: "Full catalogue" },
];

const HOW: { view: View; label: string }[] = [
  { view: "how", label: "How it works" },
  { view: "gaps", label: "Gaps and limits" },
  { view: "about", label: "About" },
];

/** The pages inside a section, as one row under the header, so every page of Explore (or of How it
 *  works) is one click from the others and the current one is marked. */
export function SectionNav({ view, onView }: Props) {
  const section = sectionOf(view);
  const items = section === "explore" ? EXPLORE : section === "how" ? HOW : null;
  if (!items) return null;
  return (
    <nav className="section-nav" aria-label={section === "explore" ? "Explore" : "How it works"}>
      <ul>
        {items.map((item) => (
          <li key={item.view}>
            {item.view === "catalogue" ? (
              <a className="section-link" href="/catalogue/">
                {item.label}
              </a>
            ) : (
              <button
                type="button"
                className="section-link"
                aria-current={view === item.view ? "page" : undefined}
                onClick={() => onView(item.view as View)}
              >
                {item.label}
              </button>
            )}
          </li>
        ))}
      </ul>
    </nav>
  );
}
