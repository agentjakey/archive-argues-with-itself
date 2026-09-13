import React from "react";

interface Props {
  children: React.ReactNode;
}

interface State {
  hasError: boolean;
}

/** Last-resort guard: a render-time exception anywhere below shows a calm card and,
 *  in the kiosk, reloads to the home screen after a few seconds (dropping the query
 *  that triggered it, so it cannot crash-loop). Without this, a thrown render
 *  white-screens the exhibit with no recovery (N6). */
export class ErrorBoundary extends React.Component<Props, State> {
  state: State = { hasError: false };

  static getDerivedStateFromError(): State {
    return { hasError: true };
  }

  componentDidCatch(error: unknown): void {
    console.error("UI crash:", error);
    if (typeof window !== "undefined") {
      const p = new URLSearchParams(window.location.search);
      const flags = ["kiosk", "offline"].filter((k) => p.get(k)).map((k) => `${k}=1`).join("&");
      window.setTimeout(() => window.location.assign(`${window.location.pathname}${flags ? `?${flags}` : ""}`), 8000);
    }
  }

  render(): React.ReactNode {
    if (!this.state.hasError) return this.props.children;
    return (
      <div className="mx-auto max-w-[1100px] px-4 py-6 sm:px-6">
        <article className="card" role="alert">
          <h2 className="font-serif text-2xl">Something went wrong on screen</h2>
          <p className="mt-3 max-w-prose leading-relaxed">
            The exhibit hit an unexpected error. It will return to the start on its own in a moment; or
            touch the screen to begin again.
          </p>
        </article>
      </div>
    );
  }
}
