"""Phase 4's bounded end-to-end run: one sub-collection we do not index yet, through every new part.

  compile   the compile job on the slice's fetched text (local executor, R2 store)
  pack      plan the slice into shards (a small target, so it makes two or three) and build each
            shard's corpus database with the corpus builder's own schema and normalizer
  embed     the embed job on each shard's passages (local executor), vectors kept with the shard
  coverage  each shard's static coverage file
  upload    shard databases, vectors and coverage files to R2 under bounded/<slice>/<shard>/
  answer    questions through the router: choose shards from coverage only, wake (load) them,
            merge with collection-wide BM25 and dense scores, one model call each (metered)
  audit     the Phase 2 audit pipeline on the answers: gates against each cited shard, the panel

    python scripts/v2/bounded_run.py compile --slice bc_govpubs
    python scripts/v2/bounded_run.py pack --slice bc_govpubs --target 12000
    python scripts/v2/bounded_run.py embed --slice bc_govpubs
    python scripts/v2/bounded_run.py coverage --slice bc_govpubs
    python scripts/v2/bounded_run.py upload --slice bc_govpubs
    python scripts/v2/bounded_run.py answer --slice bc_govpubs --questions config/bounded/bc_govpubs_questions.txt
    python scripts/v2/bounded_run.py audit --slice bc_govpubs --cap 1.00

The staging engines are not used: engine Worker changes for many shards wait for Phase 3's Gate 3.
A local engine (this script) loads each woken shard and measures that load as its wake time.
"""
from __future__ import annotations

import argparse
import gzip
import io
import json
import sqlite3
import sys
import time
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))

from archive_debugger.jobs import compile as compile_job, embed as embed_job, runner, spec as spec_mod  # noqa: E402
from archive_debugger.jobs.store import LocalStore, R2Store  # noqa: E402
from archive_debugger.shards import coverage as coverage_mod, plan as plan_mod, router  # noqa: E402

DATA = REPO / "data" / "bounded"
LEDGER = REPO / "reports" / "v2" / "scale" / "ledger.jsonl"
PHASE_CAP = 40.00
AUDIT_TIER = "INDEXED"            # searchable, unaudited: the slice has no human or calibrated audit


def env():
    from archive_debugger.local_env import load_local_env
    load_local_env(log=None)


def slice_dir(name: str) -> Path:
    return DATA / name


def cmd_compile(args) -> int:
    env()
    spec = spec_mod.load(str(REPO / "config" / "jobs" / f"compile-{args.slice}.toml"))
    store = R2Store()
    args.source = str(DATA / f"{args.slice}.txt")
    units = compile_job.prepare(spec, store, args)
    store.put(f"{spec.input_prefix}/{runner.UNITS}", "".join(json.dumps(u) + "\n" for u in units).encode())
    result = runner.run(spec, store, compile_job.make_process(spec, "local"), executor="local")
    manifest = runner.finish(spec, store)
    print(json.dumps({**result, "complete": manifest["complete"]}))
    return 0 if manifest["complete"] else 1


def compiled_units(slice_name: str) -> list:
    spec = spec_mod.load(str(REPO / "config" / "jobs" / f"compile-{slice_name}.toml"))
    store = R2Store()
    _, fingerprint = runner.read_units(store, spec)
    manifest = json.loads(store.get(f"{spec.run_prefix(fingerprint)}/manifest.json"))
    return [store.get(e["key"]) for e in manifest["units"].values()]


def cmd_pack(args) -> int:
    env()
    from archive_debugger.ingest import db as ingest_db, normalize
    units = compiled_units(args.slice)
    registry = sqlite3.connect(REPO / "data" / "registry" / "registry.db")
    docs, counts = [], {}
    for raw in units:
        for line in gzip.decompress(raw).decode("utf-8").splitlines():
            row = json.loads(line)
            if row["kind"] == "passage":
                counts[row["item_id"]] = counts.get(row["item_id"], 0) + 1
    for ident, n in counts.items():
        place, year = registry.execute(
            "SELECT d.jurisdiction, (SELECT year FROM dates WHERE doc_id = d.doc_id AND kind = 'catalogue') "
            "FROM documents d WHERE d.doc_id = ?", (f"ia:{ident}",)).fetchone() or ("unknown", None)
        docs.append((f"ia:{ident}", place or "unknown", year, n / plan_mod.PASSAGES_PER_PAGE))
    shards = plan_mod.plan(docs, target=args.target, pool_below=args.pool_below)
    out = slice_dir(args.slice) / "shards"
    summary = []
    for s in shards:
        members = {d.split(":", 1)[1] for d in s.documents}
        db_path = out / s.shard_id / "civic.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        if db_path.exists():
            db_path.unlink()
        filtered = []
        for raw in units:
            keep = [l for l in gzip.decompress(raw).decode("utf-8").splitlines()
                    if (json.loads(l).get("identifier") or json.loads(l).get("item_id")) in members]
            filtered.append(gzip.compress(("\n".join(keep) + "\n").encode("utf-8")))
        def normalize_from_registry(conn):
            # The corpus normalizer fills issuer, dates and document type; the place is the
            # registry's (one source of truth, read with the merged rules), never re-guessed here.
            normalize.normalize_items(conn, REPO / "config")
            for ident, in conn.execute("SELECT item_id FROM items").fetchall():
                place, method = registry.execute("SELECT jurisdiction, jurisdiction_method FROM documents WHERE doc_id = ?",
                                                 (f"ia:{ident}",)).fetchone() or ("unknown", "unknown")
                conn.execute("UPDATE items SET jurisdiction_norm = ?, jurisdiction_method = ? WHERE item_id = ?",
                             (place or "unknown", f"registry:{method}", ident))
            conn.commit()
        got = compile_job.pack_shard(filtered, db_path, init_db=ingest_db.init_db, normalize=normalize_from_registry)
        summary.append({**s.summary(), **{f"built_{k}": v for k, v in got.items()}})
    (slice_dir(args.slice) / "shards.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    print(json.dumps([{k: s[k] for k in ("shard_id", "first_year", "last_year", "undated", "built_items", "built_passages")}
                      for s in summary], indent=1))
    return 0


def shard_ids(slice_name: str) -> list:
    return [s["shard_id"] for s in json.loads((slice_dir(slice_name) / "shards.json").read_text(encoding="utf-8"))]


def cmd_embed(args) -> int:
    env()
    spec = spec_mod.load(str(REPO / "config" / "jobs" / "embed-sample.toml"))
    for sid in shard_ids(args.slice):
        folder = slice_dir(args.slice) / "shards" / sid
        conn = sqlite3.connect(folder / "civic.db")
        rows = [{"passage_id": r[0], "text": r[1]} for r in conn.execute("SELECT passage_id, text FROM passages ORDER BY passage_id")]
        store = LocalStore(folder / "jobs")
        units = []
        for n in range(0, len(rows), 2000):
            uid = f"{sid}-{n // 2000:04d}"
            store.put(f"{spec.input_prefix}/shards/{uid}.jsonl.gz", embed_job.write_shard(rows[n:n + 2000]))
            units.append({"id": uid})
        store.put(f"{spec.input_prefix}/{runner.UNITS}", "".join(json.dumps(u) + "\n" for u in units).encode())
        started = time.time()
        result = runner.run(spec, store, embed_job.make_process(spec, "local"), executor="local", log=lambda m: None)
        manifest = runner.finish(spec, store)
        mats, ids = [], []
        for uid in sorted(manifest["units"]):
            z = np.load(io.BytesIO(store.get(manifest["units"][uid]["key"])))
            mats.append(z["matrix"])
            ids.extend(z["ids"].tolist())
        np.save(folder / "matrix.npy", np.vstack(mats))
        np.save(folder / "ids.npy", np.array(ids))
        print(json.dumps({"shard": sid, "passages": len(ids), "seconds": round(time.time() - started, 1),
                          "per_second": round(len(ids) / max(0.001, time.time() - started), 1), **result}))
    return 0


def cmd_coverage(args) -> int:
    for sid in shard_ids(args.slice):
        folder = slice_dir(args.slice) / "shards" / sid
        cov = coverage_mod.compute(sqlite3.connect(folder / "civic.db"), sid)
        (folder / "coverage.json").write_text(json.dumps(cov), encoding="utf-8")
        print(sid, cov["passages"], len(cov["df"]), cov["jurisdictions"])
    return 0


def cmd_upload(args) -> int:
    env()
    store = R2Store()
    for sid in shard_ids(args.slice):
        folder = slice_dir(args.slice) / "shards" / sid
        for name in ("civic.db", "matrix.npy", "ids.npy", "coverage.json"):
            meta = store.put(f"bounded/{args.slice}/{sid}/{name}", (folder / name).read_bytes())
            print(f"bounded/{args.slice}/{sid}/{name}", meta["bytes"], meta["sha256"][:16])
    return 0


class LocalEngine:
    """One shard, loaded on demand: its corpus database and its vectors. Loading is its wake."""

    def __init__(self, folder: Path):
        started = time.time()
        self.conn = sqlite3.connect(folder / "civic.db", check_same_thread=False)
        self.matrix = np.load(folder / "matrix.npy")
        self.ids = np.load(folder / "ids.npy").tolist()
        self.wake_seconds = round(time.time() - started, 3)

    def hits(self, question: str, qvec: np.ndarray, k: int = 40) -> list:
        sims = self.matrix @ qvec
        top = np.argsort(-sims)[:k]
        dense = {self.ids[i]: float(sims[i]) for i in top}
        bm = router.shard_hits(self.conn, question, dense_scores=dense, limit=k)
        have = {h["passage_id"] for h in bm}
        q = list(dict.fromkeys(coverage_mod.terms(question)))
        for pid, score in dense.items():
            if pid in have:
                continue
            text = self.conn.execute("SELECT text FROM passages WHERE passage_id = ?", (pid,)).fetchone()[0]
            words = coverage_mod.terms(text)
            bm.append({"passage_id": pid, "tf": {t: words.count(t) for t in q if t in words}, "dl": len(words), "dense": score})
        return bm

    def row(self, pid: str) -> dict:
        r = self.conn.execute(
            "SELECT p.passage_id, p.item_id, p.leaf_index, p.text, g.printed_page, i.title, i.year, i.jurisdiction_norm "
            "FROM passages p JOIN pages g ON g.page_id = p.page_id JOIN items i ON i.item_id = p.item_id "
            "WHERE p.passage_id = ?", (pid,)).fetchone()
        return {"passage_id": r[0], "item_id": r[1], "leaf_index": r[2], "text": r[3], "printed_page": r[4],
                "title": r[5], "year": r[6], "jurisdiction": r[7],
                "page_deep_link": f"https://archive.org/details/{r[1]}/page/n{r[2]}"}


class MeteredClient:
    """The Anthropic client with every call reserved and recorded in the scale ledger."""

    def __init__(self, run_id: str, run_cap: float):
        import anthropic
        from archive_debugger.audit.budget import Ledger
        self.inner = anthropic.Anthropic()
        self.ledger = Ledger(LEDGER, phase_cap=PHASE_CAP)
        self.run_id, self.run_cap = run_id, run_cap
        self.messages = self

    def parse(self, **kwargs):
        from archive_debugger.audit.budget import worst_case
        chars = len(kwargs.get("system", "")) + sum(len(m["content"]) for m in kwargs["messages"])
        reservation = f"{self.run_id}:{time.time_ns()}"
        self.ledger.reserve(self.run_id, self.run_cap, "anthropic", kwargs["model"], reservation,
                            worst_case(kwargs["model"], chars, kwargs["max_tokens"]))
        try:
            resp = self.inner.messages.parse(**kwargs)
            u = resp.usage
            self.ledger.spend(self.run_id, "anthropic", kwargs["model"], int(u.input_tokens or 0), int(u.output_tokens or 0),
                              what="bounded answer")
        finally:
            self.ledger.release(self.run_id, reservation)
        return resp


def cmd_answer(args) -> int:
    env()
    from archive_debugger.generate.answer import compose, generation_meta
    from archive_debugger.generate.cli import load_generate_config, sent_temperature
    from archive_debugger.generate.llm import AnthropicLLM
    from archive_debugger.retrieve.citation import verify_citations
    from archive_debugger.retrieve.embed import FastEmbedEmbedder
    from archive_debugger.audit.prices import PRICES
    gcfg = load_generate_config(REPO / "config" / "microlog.toml")
    model = gcfg["model"]
    price_name = next(k for k in PRICES if model.startswith(k))
    folders = {sid: slice_dir(args.slice) / "shards" / sid for sid in shard_ids(args.slice)}
    coverages = [json.loads((f / "coverage.json").read_text(encoding="utf-8")) for f in folders.values()]
    embedder = FastEmbedEmbedder("sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2", 384)
    client = MeteredClient(args.run, args.cap)
    llm = AnthropicLLM(price_name, gcfg["max_tokens"], client=client, temperature=sent_temperature("anthropic", gcfg))
    gen = generation_meta(provider="anthropic", model=price_name, temperature=sent_temperature("anthropic", gcfg),
                          max_tokens=gcfg["max_tokens"], top_k=gcfg["top_k"])
    questions = [q.strip() for q in Path(args.questions).read_text(encoding="utf-8").splitlines() if q.strip() and not q.startswith("#")]
    out = []
    for question in questions:
        t0 = time.time()
        chosen, left = router.choose(question, coverages, max_engines=args.engines)
        t_route = time.time() - t0
        engines, wakes = {}, {}
        for c in chosen:
            engines[c.shard_id] = LocalEngine(folders[c.shard_id])
            wakes[c.shard_id] = engines[c.shard_id].wake_seconds
        qvec = np.array(embedder.embed_query(question), dtype=np.float32)
        qvec = qvec / (np.linalg.norm(qvec) or 1)
        t1 = time.time()
        hits_by = {sid: e.hits(question, qvec) for sid, e in engines.items()}
        merged = router.merge(question, hits_by, coverages, top_k=gcfg["top_k"])
        t_search = time.time() - t1
        hits = [{**engines[m["shard_id"]].row(m["passage_id"]), "shard_id": m["shard_id"]} for m in merged]
        owner = {h["passage_id"]: engines[h["shard_id"]] for h in hits}

        def verify(cited, retrieved):
            checks = []
            for pid in cited:
                eng = owner.get(pid)
                checks += verify_citations(eng.conn if eng else sqlite3.connect(":memory:"), [pid], retrieved) if eng else \
                    [type("Check", (), {"passage_id": pid, "ok": False})()]
            return checks
        t2 = time.time()
        answer = compose(question, hits, llm, verify, min_passages=gcfg["min_passages"], generation=gen) if hits else None
        t_answer = time.time() - t2
        out.append({"question": question, "chosen": [c.__dict__ for c in chosen], "left_out": [c.__dict__ for c in left],
                    "wake_seconds": wakes, "route_seconds": round(t_route, 3), "search_seconds": round(t_search, 3),
                    "answer_seconds": round(t_answer, 3), "evidence": hits,
                    "answer": answer.model_dump() if hasattr(answer, "model_dump") else (answer.__dict__ if answer else None),
                    "tier": {sid: AUDIT_TIER for sid in engines}})
        print(json.dumps({"question": question[:60], "shards": [c.shard_id for c in chosen], "wake": wakes,
                          "search_s": round(t_search, 2), "answer_s": round(t_answer, 2)}))
    path = slice_dir(args.slice) / f"answers-{args.run}.json"
    path.write_text(json.dumps(out, indent=1, default=str), encoding="utf-8")
    print(f"-> {path}")
    return 0


def audit_items(slice_name: str, run: str) -> list:
    """The answers' kept sentences and the answers themselves, as Phase 2 audit items."""
    from archive_debugger.audit.items import CITATION_FIELDS, ITEM_FORMAT
    answers = json.loads((slice_dir(slice_name) / f"answers-{run}.json").read_text(encoding="utf-8"))
    items = []
    for n, a in enumerate(answers, 1):
        ans = a.get("answer") or {}
        sentences = ans.get("sentences") or []
        if not sentences:
            continue
        evidence = {e["passage_id"]: e for e in a["evidence"]}
        qid = f"{slice_name}-q{n:02d}"
        text = " ".join(s["text"] for s in sentences)
        for k, s in enumerate(sentences, 1):
            cites = []
            for pid in s.get("cited_ids") or []:
                e = evidence.get(pid)
                if e is None:
                    continue
                cite = {f: e.get(f) for f in CITATION_FIELDS if f != "deep_link"}
                cite["deep_link"] = e["page_deep_link"]
                cite["text"] = e["text"]
                cites.append(cite)
            items.append({"format": ITEM_FORMAT, "kind": "sentence", "item_id": f"{qid}:s{k}", "collection": slice_name,
                          "qid": qid, "question": a["question"], "filters": {}, "sentence_no": k, "sentence": s["text"],
                          "answer_text": text, "citations": cites, "retrieved_ids": list(evidence), "source": run,
                          "writer_model": ans.get("generation", {}).get("model"), "shards": {c["passage_id"]: evidence[c["passage_id"]]["shard_id"] for c in cites}})
        items.append({"format": ITEM_FORMAT, "kind": "answer", "item_id": f"{qid}:answer", "collection": slice_name,
                      "qid": qid, "question": a["question"], "filters": {}, "answer_text": text,
                      "sentences": [s["text"] for s in sentences], "source": run,
                      "writer_model": ans.get("generation", {}).get("model")})
    return items


def cmd_audit(args) -> int:
    """The Phase 2 audit pipeline on the slice: the deterministic gates against each cited shard, the
    panel's two judges (never the model that wrote the answers), each check decided by agreement;
    disagreements go to a person (no escalation run here). Metered in the scale ledger."""
    env()
    from archive_debugger.audit import gates, judges, panel
    from archive_debugger.audit.budget import Ledger
    items = audit_items(args.slice, args.run)
    cfg = judges.load_panel()
    conflicts = judges.writer_conflicts(cfg, items)
    names = [n for n in cfg.judges if n not in conflicts]
    if len(names) < 2:
        print(f"refused: the panel {cfg.judges} includes the writer ({conflicts})")
        return 1
    folders = {sid: slice_dir(args.slice) / "shards" / sid for sid in shard_ids(args.slice)}
    conns = {sid: sqlite3.connect(f) for sid, f in ((s, folders[s] / "civic.db") for s in folders)}
    for c in conns.values():
        c.row_factory = sqlite3.Row
    gate_rows = {}
    for it in items:
        shard = next(iter((it.get("shards") or {}).values()), next(iter(conns)))
        gate_rows[it["item_id"]] = gates.run_gates(conns[shard], it)
    ledger = Ledger(LEDGER, phase_cap=PHASE_CAP)
    run_id = f"bounded-audit-{args.run}"
    records: dict = {}
    for name in names:
        spec = cfg.specs[name]
        if spec.provider == "anthropic":
            got = judges.run_anthropic_batch(spec, items, ledger, run_id, args.cap,
                                             slice_dir(args.slice) / f"audit_batch_{name}.json")
        else:
            got = judges.run_workers_ai_many(spec, items, ledger, run_id, args.cap, gateway=cfg.workers_ai_gateway)
        for r in got:
            records.setdefault(r["item_id"], {})[name] = r
    decisions = [panel.decide(it, gate_rows[it["item_id"]], tuple(names), records.get(it["item_id"], {}), None) for it in items]
    out = slice_dir(args.slice) / f"audit-{args.run}.json"
    out.write_text(json.dumps({"items": items, "gates": gate_rows, "judgments": records, "decisions": decisions},
                              indent=1, default=str), encoding="utf-8")
    tally: dict = {}
    for d in decisions:
        for check, v in (d.get("checks") or {}).items():
            key = f"{check}:{v.get('verdict') or v.get('decision') or v}"
            tally[key] = tally.get(key, 0) + 1
    from collections import Counter
    print(json.dumps({"items": len(items), "valid": dict(Counter(g["valid"] for g in gate_rows.values())),
                      "decisions": tally, "spent": round(ledger.totals(run_id).spent, 4)}, indent=1))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["compile", "pack", "embed", "coverage", "upload", "answer", "audit"])
    ap.add_argument("--slice", required=True)
    ap.add_argument("--target", type=int, default=12000)
    ap.add_argument("--pool-below", type=int, default=5000)
    ap.add_argument("--shard", type=int, default=20)
    ap.add_argument("--questions", default=None)
    ap.add_argument("--engines", type=int, default=3)
    ap.add_argument("--run", default="bounded-1")
    ap.add_argument("--cap", type=float, default=1.00)
    args = ap.parse_args(argv)
    return {"compile": cmd_compile, "pack": cmd_pack, "embed": cmd_embed, "coverage": cmd_coverage,
            "upload": cmd_upload, "answer": cmd_answer, "audit": cmd_audit}[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
