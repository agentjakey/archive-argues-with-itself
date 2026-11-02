"""The exhibit review screen: read flagged rounds in a browser and decide them from the keyboard.

    python scripts/v2/exhibit_review.py            # the rounds the checks or the reviewer flagged
    python scripts/v2/exhibit_review.py --all      # every round that could go in the deck

Opens http://127.0.0.1:8766. One round at a time: the pages with the round's quotes marked, the
claims or question, the answer, the explanation in English and French, why it was flagged, and what
the panel and the reviewer said. Each decision is written the moment it is made to
exhibit/decks/starter/author_reviews.jsonl, tied to the round's fingerprint, so a round that changes
later must be read again. Starting again resumes at the first undecided round. Archival text is
shown as text, never as HTML. The server listens on this computer only.

Keys: a approve; r reject; e edit the explanation (then Ctrl+Enter to approve with the edit); n
note; Left and Right move; ? help. Then `python scripts/v2/exhibit_deck.py decide` and `build`."""
from __future__ import annotations

import argparse
import json
import sys
import webbrowser
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "src"))

from archive_debugger.audit.records import append_jsonl, read_jsonl  # noqa: E402

WORK = REPO / "reports" / "v2" / "exhibit" / "work"
REVIEWS = REPO / "exhibit" / "decks" / "starter" / "author_reviews.jsonl"
DECISIONS = ("approve", "reject")

PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Exhibit review</title>
<style>
body{font:16px/1.45 system-ui,sans-serif;margin:0;background:#111;color:#eee}
header{position:sticky;top:0;background:#222;padding:8px 14px;display:flex;gap:16px;align-items:center;border-bottom:1px solid #444}
main{display:grid;grid-template-columns:1fr 1fr;gap:14px;padding:14px}
section{background:#1b1b1b;border:1px solid #333;border-radius:6px;padding:10px 12px}
pre{white-space:pre-wrap;font:14px/1.4 Georgia,serif;max-height:60vh;overflow:auto;background:#0b0b0b;padding:8px}
mark{background:#ffd60a;color:#000}
.flag{color:#ffab96}.ok{color:#8be39a}.muted{color:#aaa}
textarea{width:100%;min-height:5em;background:#000;color:#eee;font:inherit}
kbd{border:1px solid #666;border-radius:3px;padding:0 4px}
</style></head><body>
<header><strong id="pos"></strong><span id="status"></span><span class="muted">
<kbd>a</kbd> approve <kbd>r</kbd> reject <kbd>e</kbd> edit <kbd>n</kbd> note <kbd>&larr;</kbd><kbd>&rarr;</kbd> move</span></header>
<main><div id="left"></div><div id="right"></div></main>
<script>
let rounds=[], decided={}, i=0;
const el=(tag,text,cls)=>{const e=document.createElement(tag); if(text!==undefined) e.textContent=text; if(cls) e.className=cls; return e;};
function words(s){return (s.normalize('NFKD').replace(/[\\u0300-\\u036f]/g,'').toLowerCase().match(/[a-z0-9]+/g)||[]);}
function marked(text, quotes){
  const pre=el('pre'); const hay=[]; const re=/[\\p{L}\\p{N}]+/gu; let m;
  while((m=re.exec(text))!==null){hay.push({w:words(m[0]).join(''),s:m.index,e:m.index+m[0].length});}
  const on=new Array(text.length).fill(false);
  for(const q of quotes){const n=words(q); outer: for(let k=0;k+n.length<=hay.length;k++){for(let j=0;j<n.length;j++){if(hay[k+j].w!==n[j]) continue outer;} for(let c=hay[k].s;c<hay[k+n.length-1].e;c++) on[c]=true; break;}}
  let start=0; for(let c=1;c<=text.length;c++){ if(c===text.length||on[c]!==on[start]){ const piece=text.slice(start,c); pre.appendChild(on[start]?el('mark',piece):document.createTextNode(piece)); start=c; } }
  return pre;
}
function show(){
  const r=rounds[i]; if(!r) return;
  document.getElementById('pos').textContent=`${i+1} / ${rounds.length}  ${r.id}  (${r.mode})`;
  const d=decided[r.id]; const st=document.getElementById('status');
  st.textContent=d? `decided: ${d.decision}` : 'undecided'; st.className=d?'ok':'flag';
  const left=document.getElementById('left'), right=document.getElementById('right');
  left.replaceChildren(); right.replaceChildren();
  for(const p of r.pages){
    const s=el('section'); s.appendChild(el('h3',`${p.ref}  ${p.title}`));
    s.appendChild(el('div',`${p.issuer||''} | ${p.jurisdiction} | catalogue ${p.catalogue_date.year} | read ${p.page_date.year} (${p.page_date.method}): "${p.page_date.line||''}"`,'muted'));
    const a=el('a','open on archive.org'); a.href=p.details_url; a.target='_blank'; a.rel='noreferrer'; s.appendChild(a);
    s.appendChild(marked(p.text, r.quotes.filter(q=>q.page_ref===p.ref).map(q=>q.text)));
    left.appendChild(s);
  }
  const s=el('section');
  const play=r.play;
  if(r.mode==='same_or_not'){
    s.appendChild(el('h3','Claims')); play.claims.forEach((c,k)=>{s.appendChild(el('p',`${'AB'[k]}: ${c.text.en}`)); s.appendChild(el('p',`${'AB'[k]} fr: ${c.text.fr}`,'muted'));});
    s.appendChild(el('h3',`Answer: ${play.answer}`)); s.appendChild(el('p',JSON.stringify(play.constraints),'muted'));
  } else if(r.mode==='when_was_this'){
    s.appendChild(el('h3',`Year: ${play.year}  (${play.label.en} / ${play.label.fr})`));
  } else {
    s.appendChild(el('h3',play.question.en));
    for(const e of play.epochs){ s.appendChild(el('p',`${e.year} [${e.state}] ${e.answer.en}`)); s.appendChild(el('p',`fr: ${e.answer.fr}`,'muted')); }
  }
  s.appendChild(el('h3','Quotes')); for(const q of r.quotes) s.appendChild(el('p',`${q.id} (${q.role}, ${q.page_ref}): "${q.text}"`));
  s.appendChild(el('h3',`Explanation (${r.explanation_status})`));
  const en=el('textarea'); en.value=r.explanation.en; en.id='en'; const fr=el('textarea'); fr.value=r.explanation.fr; fr.id='fr';
  s.appendChild(en); s.appendChild(fr);
  s.appendChild(el('h3','Why flagged')); for(const f of (r.review&&r.review.flags)||[]) s.appendChild(el('p',f,'flag'));
  s.appendChild(el('h3','Panel (uncalibrated) and reviewer'));
  for(const [name,v] of Object.entries((r.review&&r.review.panel)||{})) s.appendChild(el('p',`${name}: ${v?`${v.supports}/${v.answer_correct}/${v.fair_to_visitor} ${v.notes}`:'missing'}`,'muted'));
  const rv=r.review&&r.review.reviewer; if(rv&&rv.verdicts){const v=rv.verdicts; s.appendChild(el('p',`${rv.model}: supports ${v.supports}, answer ${v.answer_correct}, fair ${v.fair_to_visitor}, french ${v.french_ok}, year ${v.year_is_publication}. ${v.notes}`));}
  const note=el('textarea'); note.id='note'; note.placeholder='note (n)'; note.value=(d&&d.notes)||''; s.appendChild(note);
  right.appendChild(s);
}
async function decide(decision, withEdit){
  const r=rounds[i];
  const body={round_id:r.id, fingerprint:r.checks.fingerprint, decision, notes:document.getElementById('note').value};
  if(withEdit){ const en=document.getElementById('en').value, fr=document.getElementById('fr').value;
    if(en!==r.explanation.en||fr!==r.explanation.fr) body.explanation={en,fr}; }
  const res=await fetch('/decide',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify(body)});
  if(!res.ok){ alert(await res.text()); return; }
  decided[r.id]=await res.json(); if(i<rounds.length-1) i++; show();
}
document.addEventListener('keydown',e=>{
  const typing=['TEXTAREA','INPUT'].includes(document.activeElement.tagName);
  if(typing){ if(e.key==='Escape') document.activeElement.blur(); if(e.key==='Enter'&&e.ctrlKey){ e.preventDefault(); decide('approve',true);} return; }
  if(e.key==='a') decide('approve',false); else if(e.key==='r') decide('reject',false);
  else if(e.key==='e'){ e.preventDefault(); document.getElementById('en').focus(); }
  else if(e.key==='n'){ e.preventDefault(); document.getElementById('note').focus(); }
  else if(e.key==='ArrowRight'){ i=Math.min(rounds.length-1,i+1); show(); }
  else if(e.key==='ArrowLeft'){ i=Math.max(0,i-1); show(); }
  else if(e.key==='?') alert('a approve, r reject, e edit explanation then Ctrl+Enter approve with the edit, n note, Esc leave a text box, arrows move');
});
fetch('/rounds').then(r=>r.json()).then(d=>{rounds=d.rounds; decided=d.decided; i=Math.max(0,rounds.findIndex(r=>!decided[r.id])); show();});
</script></body></html>"""


def latest_reviews() -> dict:
    out = {}
    if REVIEWS.exists():
        for r in read_jsonl(REVIEWS):
            out[r["round_id"]] = r
    return out


def rounds_to_review(all_rounds: bool) -> list:
    decided = json.loads((WORK / "decided.json").read_text(encoding="utf-8"))
    if all_rounds:
        return [r for r in decided if r["status"] in ("flagged", "model-reviewed", "ai-adjudicated", "ai-rejected",
                                                      "author-reviewed")]
    # A card flagged only because the reviewer did not read it (the budget covered a sample) is not
    # a finding: it waits until the deck needs it. Rounds a model adjudicated, approved or dropped,
    # wait for a person's decision, which replaces the adjudication.
    return [r for r in decided if r["status"] in ("ai-adjudicated", "ai-rejected")
            or (r["status"] == "flagged" and (r["review"] or {}).get("flags") != ["review:missing"])]


def make_handler(rounds: list, reviewer: str):
    by_id = {r["id"]: r for r in rounds}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            return

        def _send(self, status: int, body: bytes, kind: str) -> None:
            self.send_response(status)
            self.send_header("content-type", kind)
            self.send_header("content-length", str(len(body)))
            self.send_header("cache-control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path == "/":
                self._send(200, PAGE.encode("utf-8"), "text/html; charset=utf-8")
            elif self.path == "/rounds":
                decided = {k: v for k, v in latest_reviews().items()
                           if k in by_id and v.get("fingerprint") == by_id[k]["checks"]["fingerprint"]}
                self._send(200, json.dumps({"rounds": rounds, "decided": decided}).encode("utf-8"), "application/json")
            else:
                self._send(404, b"not found", "text/plain")

        def do_POST(self):
            if self.path != "/decide":
                self._send(404, b"not found", "text/plain")
                return
            body = json.loads(self.rfile.read(int(self.headers.get("content-length") or 0)).decode("utf-8"))
            rnd = by_id.get(body.get("round_id"))
            if rnd is None or body.get("decision") not in DECISIONS or body.get("fingerprint") != rnd["checks"]["fingerprint"]:
                self._send(400, b"unknown round, decision or fingerprint", "text/plain")
                return
            row = {"round_id": rnd["id"], "fingerprint": rnd["checks"]["fingerprint"], "decision": body["decision"],
                   "date": date.today().isoformat(), "reviewer": reviewer, "label": "author-reviewed",
                   "notes": str(body.get("notes") or "")[:2000]}
            exp = body.get("explanation")
            if isinstance(exp, dict) and isinstance(exp.get("en"), str) and isinstance(exp.get("fr"), str):
                row["explanation"] = {"en": exp["en"][:3000], "fr": exp["fr"][:3000]}
            append_jsonl(REVIEWS, row)
            self._send(200, json.dumps(row).encode("utf-8"), "application/json")

    return Handler


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--all", action="store_true", help="every round that could go in the deck, not only flagged ones")
    ap.add_argument("--port", type=int, default=8766)
    ap.add_argument("--reviewer", default="Jake")
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args(argv)
    rounds = rounds_to_review(args.all)
    print(f"{len(rounds)} rounds to review on http://127.0.0.1:{args.port}")
    server = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(rounds, args.reviewer))
    if not args.no_browser:
        webbrowser.open(f"http://127.0.0.1:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
