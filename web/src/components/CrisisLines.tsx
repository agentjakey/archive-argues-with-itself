import type { CrisisResource } from "../types";

interface Props {
  lines: CrisisResource[];
}

// Split a served contact instruction into text and clickable pieces: a phone number becomes a
// tel: link, a bare domain an https: link. The crisis numbers live only in crisis.py; this never
// adds a number, it only makes the strings the API already serves actionable.
const TOKEN = /([A-Za-z0-9-]+\.[A-Za-z]{2,}|\d[\d-]*\d)/g;

function telHref(token: string): string {
  const digits = token.replace(/\D/g, "");
  return digits.length >= 11 && digits.startsWith("1") ? `tel:+${digits}` : `tel:${digits}`;
}

function linkHref(link: string): string {
  return /^https?:\/\//.test(link) ? link : `https://${link}`;
}

function linkifyContact(text: string) {
  return text.split(TOKEN).map((part, i) => {
    if (!part) return null;
    if (/^[A-Za-z0-9-]+\.[A-Za-z]{2,}$/.test(part)) {
      return (
        <a key={i} className="linkish" href={linkHref(part)} target="_blank" rel="noopener noreferrer">
          {part}
        </a>
      );
    }
    if (/^\d[\d-]*\d$/.test(part)) {
      return (
        <a key={i} className="linkish" href={telHref(part)}>
          {part}
        </a>
      );
    }
    return <span key={i}>{part}</span>;
  });
}

/** Calm, plain list of support resources, from the single source of truth
 *  (src/archive_debugger/crisis.py) via the API. Phone numbers render as tel: links and web links
 *  as https: links, so every reference is actionable; the text is otherwise verbatim. Static,
 *  works offline. */
export function CrisisLines({ lines }: Props) {
  if (!lines || lines.length === 0) return null;
  return (
    <div className="mt-3">
      <p className="font-sans text-xs uppercase tracking-wide text-muted">If you need support</p>
      <ul className="mt-2 space-y-2">
        {lines.map((l) => (
          <li key={l.key} className="text-sm">
            <span className="font-semibold">{l.label}</span>: {linkifyContact(l.contact)}
            <div className="text-muted">For: {l["for"]}</div>
            <div className="text-muted">Hours: {l.hours}</div>
            {l.link ? (
              <div>
                <a className="linkish" href={linkHref(l.link)} target="_blank" rel="noopener noreferrer">
                  {l.link}
                </a>
              </div>
            ) : null}
          </li>
        ))}
      </ul>
    </div>
  );
}
