"""The calibration form: label the kit's items in a browser, from the keyboard, answer by answer.

    python scripts/v2/calibration_form.py                       # label the kit
    python scripts/v2/calibration_form.py --relabel 30 --seed 7 # a week later: 30 labelled items, blind

Opens http://127.0.0.1:8765. The kit comes answer by answer: first the whole answer, labelled once
on ANSWERS, then the answer's sampled sentences, each labelled on SUPPORTS and IN SCOPE. Each label
is written to the labels file the moment it is saved, so closing the browser or the server loses
nothing; starting again resumes at the first unlabelled item. The labels file is the export
(docs/formats/audit.md). Only the kit's own items are shown, never the v1 decision, a gate flag or
a judge's verdict. Archival text is shown as text and never interpreted as HTML. The server listens
on this computer only.

Keys: on an answer, q w e answers (pass, partial, fail); on a sentence, 1 2 3 supports (pass,
partial, fail) and a s d in scope (pass, fail, unclear). n note; Enter save and next; Left and Right
move; ? help."""
from __future__ import annotations

import argparse
import json
import random
import sys
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "src"))

from archive_debugger.audit.records import append_jsonl, read_jsonl  # noqa: E402
from archive_debugger.audit.run import AUDIT_DIR  # noqa: E402

KIT_DIR = AUDIT_DIR / "calibration"
CLASSES = {"supports": ("pass", "partial", "fail"), "answers": ("pass", "partial", "fail"),
           "in_scope": ("pass", "fail", "unclear")}
KIND_CHECKS = {"sentence": ("supports", "in_scope"), "answer": ("answers",)}
LABELER = "author"


def latest_labels(path: Path) -> dict:
    out = {}
    for row in read_jsonl(path):
        out[row["item_id"]] = row
    return out


def valid_label(body: dict, kinds: dict) -> str | None:
    """kinds: {item_id: kind} for the items on offer."""
    kind = kinds.get(body.get("item_id"))
    if kind is None:
        return "unknown item"
    for check in KIND_CHECKS[kind]:
        if body.get(check) not in CLASSES[check]:
            return f"{check} must be one of {CLASSES[check]}"
    extra = [c for c in CLASSES if c not in KIND_CHECKS[kind] and body.get(c) is not None]
    if extra:
        return f"a {kind} item is not labelled on {extra}"
    if not isinstance(body.get("note", ""), str) or len(body.get("note", "")) > 2000:
        return "note must be text under 2000 characters"
    return None


def label_row(body: dict, kind: str, mode: str, kit_version: str) -> dict:
    row = {"item_id": body["item_id"], "kind": kind}
    for check in KIND_CHECKS[kind]:
        row[check] = body[check]
    row.update({"note": body.get("note", ""), "labeler": LABELER, "review": "author-reviewed", "mode": mode,
                "kit_version": kit_version, "labeled_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
    return row


def make_handler(kit: list, labels_path: Path, mode: str, kit_version: str):
    kinds = {it["item_id"]: it.get("kind", "sentence") for it in kit}
    page = PAGE.replace("__MODE__", mode)

    class Handler(BaseHTTPRequestHandler):
        def _send(self, status: int, body: bytes, content_type: str) -> None:
            self.send_response(status)
            self.send_header("content-type", content_type)
            self.send_header("cache-control", "no-store")
            self.send_header("content-security-policy",
                             "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, fmt, *args):
            return

        def do_GET(self):
            if self.path == "/":
                self._send(200, page.encode("utf-8"), "text/html; charset=utf-8")
            elif self.path == "/api/state":
                body = {"items": kit, "labels": latest_labels(labels_path), "mode": mode}
                self._send(200, json.dumps(body).encode("utf-8"), "application/json")
            else:
                self._send(404, b"not found", "text/plain")

        def do_POST(self):
            if self.path != "/api/label":
                self._send(404, b"not found", "text/plain")
                return
            length = int(self.headers.get("content-length") or 0)
            try:
                body = json.loads(self.rfile.read(min(length, 100_000)).decode("utf-8"))
            except ValueError:
                self._send(400, b"not JSON", "text/plain")
                return
            problem = valid_label(body, kinds)
            if problem:
                self._send(400, problem.encode("utf-8"), "text/plain")
                return
            row = label_row(body, kinds[body["item_id"]], mode, kit_version)
            append_jsonl(labels_path, row)
            self._send(200, json.dumps(row).encode("utf-8"), "application/json")

    return Handler


def relabel_sample(kit: list, done: dict, count: int, seed: int) -> list:
    """`count` labelled items, blind, in a seeded random order. Each sentence keeps its answer's
    text for context, but the answer's own label is not shown."""
    pool = [it for it in kit if it["item_id"] in done]
    if len(pool) < count:
        raise SystemExit(f"only {len(pool)} labelled items; cannot re-label {count}")
    chosen = random.Random(f"relabel:{seed}").sample(pool, count)
    out = []
    for n, it in enumerate(chosen):
        row = dict(it)
        row["kit_position"], row["kit_batch"] = n + 1, 1
        out.append(row)
    return out


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--kit", type=Path, default=KIT_DIR / "kit.jsonl")
    parser.add_argument("--labels", type=Path, default=None)
    parser.add_argument("--relabel", type=int, default=0, help="blind re-label this many already labelled items")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args(argv)
    kit = read_jsonl(args.kit)
    if not kit:
        raise SystemExit(f"no kit at {args.kit}: run scripts/v2/calibration_kit.py first")
    kit_version = kit[0]["kit_version"]
    first_labels = args.kit.parent / "labels.jsonl"
    if args.relabel:
        kit = relabel_sample(kit, latest_labels(first_labels), args.relabel, args.seed)
        mode, labels_path = "relabel", args.labels or args.kit.parent / f"labels_relabel_{args.seed}.jsonl"
    else:
        mode, labels_path = "first", args.labels or first_labels
    server = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(kit, labels_path, mode, kit_version))
    url = f"http://127.0.0.1:{args.port}/"
    print(f"{len(kit)} items ({mode}); labels go to {labels_path}; open {url} (Ctrl+C to stop)")
    if not args.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Calibration labels</title>
<style>
:root { --ink:#1c1a17; --muted:#6b655c; --paper:#f6f1e7; --sheet:#fcfaf4; --rule:#d9d2c3; --mark:#fff1b8; --ok:#1d5f3a; --bad:#8a2b1d; }
body { margin:0; background:var(--paper); color:var(--ink); font:16px/1.5 system-ui, "Segoe UI", Arial, sans-serif; }
main { max-width:1200px; margin:0 auto; padding:16px; display:grid; grid-template-columns: 1fr 360px; gap:20px; }
@media (max-width: 900px) { main { grid-template-columns: 1fr; } }
header { max-width:1200px; margin:0 auto; padding:12px 16px 0; display:flex; gap:16px; flex-wrap:wrap; align-items:baseline; }
h1 { font-size:18px; margin:0; } .muted { color:var(--muted); font-size:14px; }
.card { background:var(--sheet); border:1px solid var(--rule); border-radius:6px; padding:12px 14px; margin-bottom:12px; }
.label { font-size:12px; text-transform:uppercase; letter-spacing:.05em; color:var(--muted); }
.unit { font-weight:600; }
.sentence { font-size:20px; font-family: Georgia, serif; background:var(--mark); padding:6px 8px; border-radius:4px; }
.whole { font-size:18px; font-family: Georgia, serif; }
.whole ol { margin:0; padding-left:1.5em; } .whole li { margin-bottom:6px; }
.answer span.cur { background:var(--mark); }
aside > .card { position:sticky; top:12px; }
.page { white-space:pre-wrap; font-family: Georgia, serif; font-size:15px; max-height:60vh; overflow:auto; }
.meta { font-size:13px; color:var(--muted); }
fieldset { border:1px solid var(--rule); border-radius:6px; margin:0 0 10px; padding:8px 10px; }
fieldset[hidden] { display:none; }
legend { font-weight:600; }
button.opt { margin:2px 4px 2px 0; padding:6px 10px; border:1px solid var(--ink); background:var(--sheet); border-radius:4px; cursor:pointer; font:inherit; }
button.opt[aria-pressed="true"] { background:var(--ink); color:var(--sheet); }
kbd { border:1px solid var(--rule); border-radius:3px; padding:0 4px; font-size:12px; background:#fff; }
textarea { width:100%; box-sizing:border-box; min-height:60px; font:inherit; }
#status { min-height:1.5em; } .saved { color:var(--ok); } .err { color:var(--bad); }
:focus-visible { outline:3px solid #1f4e9c; outline-offset:2px; }
</style></head><body>
<header><h1>Calibration labels (__MODE__)</h1><span id="progress" class="muted"></span>
<span class="muted">Keys: answer <kbd>q</kbd><kbd>w</kbd><kbd>e</kbd>; sentence <kbd>1</kbd><kbd>2</kbd><kbd>3</kbd> supports,
<kbd>a</kbd><kbd>s</kbd><kbd>d</kbd> in scope; <kbd>n</kbd> note, <kbd>Enter</kbd> save and next, <kbd>&larr;</kbd><kbd>&rarr;</kbd> move</span></header>
<main>
<section aria-label="Item">
  <div class="card"><div class="label">Question</div><div id="question"></div><div id="filters" class="meta"></div></div>
  <div id="answer-unit" class="card" hidden><div class="label unit">Whole answer: does it answer the question?</div><div id="whole" class="whole"></div></div>
  <div id="sentence-unit" hidden>
    <div class="card"><div class="label unit">Sentence to judge</div><div id="sentence" class="sentence"></div></div>
    <div id="pages"></div>
    <details class="card"><summary class="label">The whole answer (the sentence is highlighted)</summary><div id="answer" class="answer"></div></details>
  </div>
</section>
<aside aria-label="Labels">
  <div class="card">
    <fieldset id="f-answers"><legend>Answers</legend><div id="g-answers"></div><div class="meta">Does the whole answer answer the question asked?</div></fieldset>
    <fieldset id="f-supports"><legend>Supports</legend><div id="g-supports"></div><div class="meta">Is every claim in the sentence on the cited page?</div></fieldset>
    <fieldset id="f-in_scope"><legend>In scope</legend><div id="g-in_scope"></div><div class="meta">Does the page fit the question's period, place, population, program and measure?</div></fieldset>
    <label for="note" class="label">Note (optional)</label><textarea id="note"></textarea>
    <p><button class="opt" id="save">Save and next (Enter)</button> <button class="opt" id="prev">Previous</button> <button class="opt" id="next">Next</button></p>
    <div id="status" role="status" aria-live="polite"></div>
  </div>
</aside>
</main>
<script>
"use strict";
const KEYS = { supports: ["1","2","3"], answers: ["q","w","e"], in_scope: ["a","s","d"] };
const CLASSES = { supports: ["pass","partial","fail"], answers: ["pass","partial","fail"], in_scope: ["pass","fail","unclear"] };
const KIND_CHECKS = { sentence: ["supports","in_scope"], answer: ["answers"] };
let items = [], labels = {}, index = 0, current = {};
function kindOf(it) { return it.kind || "sentence"; }
function el(tag, text, cls) { const e = document.createElement(tag); if (text !== undefined) e.textContent = text; if (cls) e.className = cls; return e; }
function status(text, cls) { const s = document.getElementById("status"); s.textContent = text; s.className = cls || ""; }
function buildGroups(kind) {
  for (const check of Object.keys(CLASSES)) {
    const on = KIND_CHECKS[kind].includes(check);
    document.getElementById("f-" + check).hidden = !on;
    const g = document.getElementById("g-" + check); g.replaceChildren();
    if (!on) continue;
    CLASSES[check].forEach((cls, n) => {
      const b = el("button", cls + " (" + KEYS[check][n] + ")", "opt"); b.type = "button";
      b.setAttribute("aria-pressed", "false"); b.dataset.check = check; b.dataset.cls = cls;
      b.addEventListener("click", () => choose(check, cls)); g.appendChild(b);
    });
  }
}
function choose(check, cls) {
  if (!KIND_CHECKS[kindOf(items[index])].includes(check)) return;
  current[check] = cls;
  document.querySelectorAll('button.opt[data-check="' + check + '"]').forEach(b => b.setAttribute("aria-pressed", String(b.dataset.cls === cls)));
}
function showAnswer(it) {
  const whole = document.getElementById("whole"); whole.replaceChildren();
  const list = el("ol");
  (it.sentences || [it.answer_text]).forEach(s => list.appendChild(el("li", s)));
  whole.appendChild(list);
}
function showSentence(it) {
  document.getElementById("sentence").textContent = it.sentence;
  const ans = document.getElementById("answer"); ans.replaceChildren();
  const at = it.answer_text.indexOf(it.sentence);
  if (at >= 0) { ans.append(it.answer_text.slice(0, at)); ans.append(el("span", it.sentence, "cur")); ans.append(it.answer_text.slice(at + it.sentence.length)); }
  else ans.textContent = it.answer_text;
  const pages = document.getElementById("pages"); pages.replaceChildren();
  it.citations.forEach((c, n) => {
    const card = el("div", undefined, "card");
    card.appendChild(el("div", "Cited page " + (n + 1), "label"));
    card.appendChild(el("div", (c.title || "") + " (" + (c.year || "undated") + ", " + (c.jurisdiction || "unknown") + ", leaf " + c.leaf_index + ")", "meta"));
    const link = el("a", "Open this page on archive.org"); link.href = c.deep_link; link.target = "_blank"; link.rel = "noopener noreferrer";
    card.appendChild(link);
    card.appendChild(el("div", c.text || "", "page"));
    pages.appendChild(card);
  });
}
function show(i) {
  index = Math.max(0, Math.min(items.length - 1, i));
  const it = items[index], kind = kindOf(it);
  const done = items.filter(x => labels[x.item_id]).length;
  document.getElementById("progress").textContent = "Batch " + it.kit_batch + ", item " + it.kit_position + " of " + items.length + " (" + kind + "); " + done + " labelled";
  document.getElementById("question").textContent = it.question;
  const f = it.filters || {}; document.getElementById("filters").textContent = Object.keys(f).length ? "Filters: " + JSON.stringify(f) : "";
  document.getElementById("answer-unit").hidden = kind !== "answer";
  document.getElementById("sentence-unit").hidden = kind !== "sentence";
  if (kind === "answer") showAnswer(it); else showSentence(it);
  const prior = labels[it.item_id];
  current = {};
  buildGroups(kind);
  if (prior) for (const c of KIND_CHECKS[kind]) if (prior[c]) choose(c, prior[c]);
  document.getElementById("note").value = prior ? (prior.note || "") : "";
  status(prior ? "Labelled before; saving again replaces it." : "");
  window.scrollTo(0, 0);
}
async function save() {
  const it = items[index];
  for (const check of KIND_CHECKS[kindOf(it)]) if (!current[check]) { status("Choose a label for " + check.replace("_", " ") + " first.", "err"); return; }
  const body = { item_id: it.item_id, ...current, note: document.getElementById("note").value };
  const res = await fetch("/api/label", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) });
  if (!res.ok) { status("Not saved: " + await res.text(), "err"); return; }
  labels[it.item_id] = await res.json();
  const next = items.findIndex((x, n) => n > index && !labels[x.item_id]);
  if (next >= 0) { show(next); status("Saved.", "saved"); }
  else if (index < items.length - 1) { show(index + 1); status("Saved.", "saved"); }
  else status("Saved. That was the last item.", "saved");
}
document.addEventListener("keydown", (e) => {
  const inNote = document.activeElement && document.activeElement.id === "note";
  if (inNote) { if (e.key === "Escape") document.activeElement.blur(); if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) { e.preventDefault(); save(); } return; }
  if (e.ctrlKey || e.metaKey || e.altKey) return;
  for (const check of Object.keys(KEYS)) { const n = KEYS[check].indexOf(e.key.toLowerCase()); if (n >= 0) { choose(check, CLASSES[check][n]); e.preventDefault(); return; } }
  if (e.key === "Enter") { e.preventDefault(); save(); }
  else if (e.key === "ArrowRight") show(index + 1);
  else if (e.key === "ArrowLeft") show(index - 1);
  else if (e.key === "n") { e.preventDefault(); document.getElementById("note").focus(); }
  else if (e.key === "?") status("Answer: q w e. Sentence: 1 2 3 supports, a s d in scope. n note (Esc leaves it, Ctrl+Enter saves), Enter save and next, arrows move.");
});
document.getElementById("save").addEventListener("click", save);
document.getElementById("prev").addEventListener("click", () => show(index - 1));
document.getElementById("next").addEventListener("click", () => show(index + 1));
fetch("/api/state").then(r => r.json()).then(state => {
  items = state.items.sort((a, b) => a.kit_position - b.kit_position); labels = state.labels || {};
  const first = items.findIndex(x => !labels[x.item_id]);
  show(first >= 0 ? first : 0);
});
</script></body></html>
"""

if __name__ == "__main__":
    sys.exit(main())
