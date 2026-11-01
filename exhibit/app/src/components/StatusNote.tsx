// What checked this round, said plainly on the screen: a person, or AI judges whose accuracy has
// not yet been measured. A model-drafted explanation says so.
import type { Round } from "../lib/deck";
import type { Strings } from "../lib/strings";

export function StatusNote({ round, t }: { round: Round; t: Strings }) {
  const checked = round.status === "author-reviewed" ? t.status.authorReviewed : t.status.modelReviewed;
  const drafted = round.explanation_status === "model-drafted" ? ` ${t.status.drafted}` : "";
  return (
    <p className="status-note">
      {checked}
      {drafted}
    </p>
  );
}
