/** Agora's split bar: wherever two records are compared, a thin bar in the two split colours sits
 *  above them, and each record's year takes its half's colour. The bar is decorative (each record is
 *  already named by its year and its "Then" / "Later" label), so colour never carries meaning alone. */
export function SplitBar() {
  return (
    <span className="split-bar" aria-hidden="true">
      <span className="split-a" />
      <span className="split-b" />
    </span>
  );
}

/** The class that colours the first or second record's year to match its half of the bar. */
export function splitLabel(index: number): string {
  return index === 0 ? "split-label-a" : "split-label-b";
}
