export default function Home() {
  return (
    <main style={{ maxWidth: 720, margin: "0 auto", padding: "3rem 1.5rem" }}>
      <h1>The Archive Argues With Itself</h1>
      <p>
        A civic memory debugger for Canada&apos;s public record. Ask a question
        and see more than an answer: the pages behind it, how official language
        changes over time, which jurisdictions are represented, and where the
        archive is sparse or uncertain.
      </p>
      <p>Two linked views will live here:</p>
      <ul>
        <li>
          <strong>Evidence timeline</strong> &mdash; page-level sources ordered
          by date, showing how claims and language change.
        </li>
        <li>
          <strong>Coverage view</strong> &mdash; where the archive is thin,
          undated, or unevenly represented by jurisdiction.
        </li>
      </ul>
      <p>
        <em>Scaffold only. No data is wired up yet.</em>
      </p>
    </main>
  );
}
