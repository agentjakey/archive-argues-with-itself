import type { CorpusFacts } from "../types";
import { CorpusStrip } from "./CorpusStrip";
import { KioskQr } from "./KioskQr";

interface Props {
  corpus: CorpusFacts | null;
  kiosk: boolean;
}

export function Header({ corpus, kiosk }: Props) {
  return (
    <header className="mb-6">
      <div className="flex items-start justify-between gap-6">
        <div>
          <h1 className="font-serif text-3xl leading-tight">Archive Argues With Itself</h1>
          <p className="mt-2 max-w-prose text-muted">
            An evidence trail with page-level provenance over Canadian government public-health
            publications, 1960 to 2009. Not a chatbot.
          </p>
        </div>
        {kiosk && <KioskQr />}
      </div>
      <CorpusStrip corpus={corpus} />
    </header>
  );
}
