import type { EditorialNote } from "../types";

interface Props {
  notes?: EditorialNote[] | null;
  className?: string;
}

/** Dated editorial notes, shown in full and in date order. A note sits beside what it corrects and
 *  never replaces it: the story or the stored answer is still shown as it was. */
export function EditorialNotes({ notes, className = "" }: Props) {
  if (!notes || notes.length === 0) return null;
  return (
    <aside className={`max-w-prose border-l-2 border-rule pl-4 ${className}`} aria-label="Editorial notes">
      {notes.map((n) => (
        <p key={n.id} className="mb-2 text-sm text-ink">
          <span className="font-sans text-xs uppercase tracking-wide text-muted">Editorial note, {n.date}</span>{" "}
          {n.text}
        </p>
      ))}
    </aside>
  );
}
