import { useState } from "react";

/** Copy text to the clipboard; false when the browser refuses (no permission, an old browser). */
export async function copyText(text: string): Promise<boolean> {
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch {
    // fall through to the manual copy below
  }
  return false;
}

/** A small "Copy" button that says what happened, in words a screen reader hears too. When the
 *  browser will not copy, the text is shown selected so it can be copied by hand. */
export function CopyButton({ text, label, done = "Copied" }: { text: () => string; label: string; done?: string }) {
  const [state, setState] = useState<"idle" | "copied" | "manual">("idle");
  const value = state === "manual" ? text() : "";
  return (
    <span className="copy-button">
      <button
        type="button"
        className="chip chip-quiet"
        onClick={async () => {
          const ok = await copyText(text());
          setState(ok ? "copied" : "manual");
          if (ok) window.setTimeout(() => setState("idle"), 2500);
        }}
      >
        {label}
      </button>
      <span role="status" className={state === "copied" ? "copy-status" : "sr-only"}>
        {state === "copied" ? done : ""}
      </span>
      {state === "manual" && (
        <input
          className="copy-manual"
          readOnly
          value={value}
          aria-label="Copy this text"
          ref={(el) => el?.select()}
        />
      )}
    </span>
  );
}

/** Under a result: copy a link that reopens this exact answer (the URL carries the question, the
 *  filters, the collection and any pinned pages), and print it. */
export function ShareBar() {
  return (
    <div className="share-bar" role="group" aria-label="Share or keep this answer">
      <CopyButton text={() => window.location.href} label="Copy link" done="Link copied" />
      <button type="button" className="chip chip-quiet" onClick={() => window.print()}>
        Print
      </button>
    </div>
  );
}
