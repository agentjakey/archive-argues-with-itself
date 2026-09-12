interface Props {
  onAbout?: () => void;
}

export function Footer({ onAbout }: Props) {
  return (
    <footer className="mt-12 border-t border-rule pt-4 text-sm text-muted">
      <p>
        Built during the AI Builders Fellowship of the BC + AI Ecosystem, with the Internet Archive.{" "}
        <a className="linkish" href="https://archive-argues-with-itself-production.up.railway.app" target="_blank" rel="noopener noreferrer">
          Live demo
        </a>
        {", "}
        <a className="linkish" href="https://github.com/agentjakey/archive-argues-with-itself" target="_blank" rel="noopener noreferrer">
          source on GitHub
        </a>
        , MIT. Evidence links open archive.org; page images are served by archive.org and not redistributed;
        the publications remain under their own terms.
        {onAbout && (
          <>
            {" "}
            <button type="button" className="linkish" onClick={onAbout}>
              About
            </button>
            .
          </>
        )}
      </p>
    </footer>
  );
}
