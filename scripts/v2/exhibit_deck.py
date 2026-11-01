"""Build the exhibit's starter deck (docs/formats/exhibit-deck.md), one stage at a time. Every stage
reads and writes plain files under reports/v2/exhibit/work/ (private), so a stopped run resumes at
the stage it stopped in, and every paid stage is metered in the exhibit's own ledger.

  mine      candidate pages and pairs (no network, no model)
  pools     the Time Dial's evidence pools from the frozen retrieval (local, no model)
  draft     Sonnet 5.5 drafts When Was This? cards, Same or Not? rounds and Time Dial steps (paid)
  check     the builder's refusal checks on every draft (no model)
  panel     the audit panel judges every round the builder kept (paid, uncalibrated until Gate 2)
  review    the reviewer model reads every round the builder kept (paid)
  decide    statuses from the checks, the panel, the reviewer and Jake's reviews; the deck's choice
  gaphunt   Gap Hunt's grid from the indexed collections and the catalogue counts
  build     the published deck: site/exhibit/deck.json and its rejected file
  status    counts and spend so far

    python scripts/v2/exhibit_deck.py mine
    python scripts/v2/exhibit_deck.py draft --run draft-1 --cap 2.50 [--limit 5]
    python scripts/v2/exhibit_deck.py check
    python scripts/v2/exhibit_deck.py panel --run panel-1 --cap 1.50
    python scripts/v2/exhibit_deck.py review --run review-1 --cap 5.00
    python scripts/v2/exhibit_deck.py decide && python scripts/v2/exhibit_deck.py build --deck-id starter-1
"""
from __future__ import annotations

import argparse
import json
import sys
import tomllib
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))

from archive_debugger.audit import judges  # noqa: E402
from archive_debugger.audit.budget import BudgetExceeded, Ledger  # noqa: E402
from archive_debugger.audit.records import append_jsonl, read_jsonl  # noqa: E402
from archive_debugger.exhibit import candidates, deck as deck_mod, gaphunt, llm  # noqa: E402
from archive_debugger.exhibit import pages as pages_mod, prompts, rounds, settings, timedial  # noqa: E402

DECK_SOURCE = REPO / "exhibit" / "decks" / "starter"
WORK = REPO / "reports" / "v2" / "exhibit" / "work"
PUBLISHED = REPO / "site" / "exhibit"
AUTHOR_REVIEWS = DECK_SOURCE / "author_reviews.jsonl"
BUILDER_VERSION = "1"


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=1, ensure_ascii=True, sort_keys=True) + "\n", encoding="utf-8", newline="\n")


def read_json(path: Path, default=None):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


class Corpora:
    """One read-only connection per collection, opened on first use."""

    def __init__(self):
        self.conns, self.configs = {}, {}

    def __call__(self, name: str):
        if name not in self.conns:
            self.configs[name], self.conns[name] = pages_mod.open_collection(name)
        return self.conns[name]


def load_env() -> None:
    from archive_debugger.local_env import load_local_env
    load_local_env(log=None)


def ledger_for(s: settings.Settings) -> Ledger:
    return Ledger(s.ledger, phase_cap=s.phase_cap_usd)


# --- mine -----------------------------------------------------------------------------------------

def cmd_mine(args, s: settings.Settings) -> int:
    """Mine candidates with one mining file; candidates from earlier rounds are kept and their items
    are not mined again."""
    cfg = tomllib.loads((DECK_SOURCE / args.config).read_text(encoding="utf-8"))
    corpora = Corpora()
    earlier = read_json(WORK / "candidates.json") or {"when": [], "pairs": []}
    seen_items = {c["item_id"] for c in earlier["when"]}
    seen_items |= {p[k]["item_id"] for p in earlier["pairs"] for k in ("a", "b")}
    when, pairs = list(earlier["when"]), list(earlier["pairs"])
    for name in s.collections:
        conn = corpora(name)
        found = candidates.when_candidates(conn, name, s.care, cfg["when_was_this"], seed=cfg["seed"],
                                           exclude_items=seen_items)
        seen_items.update(c["item_id"] for c in found)
        when += found
        pairs += [p for p in candidates.pair_candidates(conn, name, s.care, cfg["same_or_not"], seed=cfg["seed"])
                  if p["a"]["item_id"] not in seen_items and p["b"]["item_id"] not in seen_items]
    write_json(WORK / "candidates.json", {"when": when, "pairs": pairs, "mined_at": now(), "seed": cfg["seed"]})
    print(f"when {len(when)}, pairs {len(pairs)} -> {WORK / 'candidates.json'}")
    return 0


# --- draft ----------------------------------------------------------------------------------------

def _when_pages(corpora, s, cands) -> dict:
    out = {}
    for c in cands:
        page = pages_mod.page_record(corpora(c["collection"]), c["collection"], c["item_id"], c["leaf"],
                                     keep_quotes=[], max_chars=s.max_page_chars)
        if page is not None:
            out[page["ref"]] = page
    return out


def _pair_pages(corpora, s, pair) -> tuple:
    conn = corpora(pair["collection"])
    a = pages_mod.page_record(conn, pair["collection"], pair["a"]["item_id"], pair["a"]["leaf"],
                              keep_quotes=[pair["phrase"]], max_chars=s.max_page_chars)
    b = pages_mod.page_record(conn, pair["collection"], pair["b"]["item_id"], pair["b"]["leaf"],
                              keep_quotes=[pair["phrase"]], max_chars=s.max_page_chars)
    return a, b


def _dial_pools(corpora, s) -> list:
    cfg = tomllib.loads((DECK_SOURCE / "time_dial.toml").read_text(encoding="utf-8"))
    from archive_debugger import scopes
    from archive_debugger.retrieve.search import Retriever
    coll_name = cfg["collection"]
    conn = corpora(coll_name)
    coll = corpora.configs[coll_name]
    # The collection's own scope pins the retriever to its databases; without it the .env's CIVIC_*
    # paths (the pilot's) would win.
    scope = scopes.resolve_scope(coll.scope)
    with scopes.activate(scope):
        retriever = Retriever(scope.config_path)
    out = []
    try:
        for q in cfg["questions"]:
            pool = timedial.gather_pool(retriever, conn, coll_name, q, cfg["decades"], per_decade=cfg["pages_per_decade"],
                                        rules=s.care, max_chars=s.max_page_chars)
            counts = timedial.year_counts(conn, q["terms"], s.dial_first_year, s.dial_last_year, q.get("jurisdiction"))
            extra = timedial.dial_extra(counts, coll.period, s.dial_first_year, s.dial_last_year)
            out.append({"question": q, "pool": pool, "extra": extra})
            print(f"dial {q['id']}: {len(pool)} pages, steps at {timedial.step_years(pool)}")
    finally:
        retriever.close()
    return out


def cmd_pools(args, s: settings.Settings) -> int:
    """The Time Dial pools: the frozen retrieval, once per question and decade (local, no model)."""
    pools = _dial_pools(Corpora(), s)
    write_json(WORK / "dial_pools.json", pools)
    return 0


def cmd_draft(args, s: settings.Settings) -> int:
    load_env()
    cand = read_json(WORK / "candidates.json")
    if cand is None:
        print("run `mine` first")
        return 1
    corpora = Corpora()
    ledger = ledger_for(s)
    requests, meta = {}, {}
    done = {r["draft_key"] for r in read_jsonl(WORK / "drafts.jsonl")} if (WORK / "drafts.jsonl").exists() else set()
    if args.redo_refused:
        done -= redo_keys()
    modes = args.modes.split(",")
    if "when" in modes:
        pages = _when_pages(corpora, s, cand["when"][: args.limit or None])
        for ref, page in pages.items():
            key = f"when|{ref}"
            if key in done:
                continue
            requests[key] = llm.anthropic_request(s.writer, prompts.WHEN_SYSTEM, prompts.when_user(page), prompts.WHEN_SCHEMA,
                                                  max_tokens=2500, effort=s.writer_effort)
            meta[key] = {"mode": "when", "page": page}
    if "same" in modes:
        for pair in cand["pairs"][: args.limit or None]:
            a, b = _pair_pages(corpora, s, pair)
            if a is None or b is None:
                continue
            key = f"same|{a['ref']}|{b['ref']}"
            if key in done:
                continue
            requests[key] = llm.anthropic_request(s.writer, prompts.SAME_SYSTEM, prompts.same_user(a, b), prompts.SAME_SCHEMA,
                                                  max_tokens=3500, effort=s.writer_effort)
            meta[key] = {"mode": "same", "pair": pair, "a": a, "b": b}
    if "dial" in modes:
        pools = read_json(WORK / "dial_pools.json")
        if pools is None:
            pools = _dial_pools(corpora, s)
            write_json(WORK / "dial_pools.json", pools)
        for entry in pools[: args.limit or None]:
            q = entry["question"]
            for year in timedial.step_years(entry["pool"]):
                key = f"dial|{q['id']}|{year}"
                if key in done:
                    continue
                step = timedial.step_pages(entry["pool"], year)
                requests[key] = llm.anthropic_request(s.writer, prompts.DIAL_SYSTEM, prompts.dial_user(q["en"], year, step),
                                                      prompts.DIAL_SCHEMA, max_tokens=3000, effort=s.writer_effort)
                meta[key] = {"mode": "dial", "question_id": q["id"], "year": year, "pages": [p["ref"] for p in step]}
    if not requests:
        print("nothing to draft")
        return 0
    print(f"drafting {len(requests)} with {s.writer} (run {args.run}, cap ${args.cap:.2f})")
    errors = total = 0
    try:
        for n, chunk in enumerate(chunks(requests, args.chunk)):
            replies = llm.run_anthropic_batch(chunk, ledger, args.run, args.cap, WORK / f"batch_{args.run}_{n}.json",
                                              what="draft")
            for key, result in replies.items():
                append_jsonl(WORK / "drafts.jsonl", {"draft_key": key, "meta": meta.get(key), **result, "drafted_at": now()})
            errors += sum(1 for r in replies.values() if r["error"])
            total += len(replies)
    except BudgetExceeded as exc:
        print(f"STOPPED: {exc}")
        return 2
    print(f"{total} replies, {errors} errors; spent ${ledger.totals(args.run).spent:.4f} this run")
    return 0


def redo_keys() -> set:
    """Draft keys to draft again: every Time Dial step, and every card or pair, that the builder
    refused only because a quote was not on its page. A new draft replaces the old one as a new
    model draft; nothing a model wrote is edited."""
    keys = set()
    for rnd in read_json(WORK / "checked.json") or []:
        reasons = rnd["checks"]["refusals"]
        if not reasons or not all(r.startswith("quote_not_on_page:") for r in reasons):
            continue
        if rnd["mode"] == "time_dial":
            for reason in reasons:
                qid = reason.split(":", 1)[1]
                year = qid[1:qid.index("q")]
                keys.add(f"dial|{rnd['play']['question_id']}|{year}")
        elif rnd["mode"] == "when_was_this":
            keys.add(f"when|{rnd['pages'][0]['ref']}")
        else:
            keys.add(f"same|{rnd['pages'][0]['ref']}|{rnd['pages'][1]['ref']}")
    return keys


def chunks(requests: dict, size: int) -> list:
    """Requests in batches small enough that one batch's worst case fits under a run cap; a batch
    reserves its worst case and the reservation is replaced by the actual cost when it ends."""
    keys = list(requests)
    return [{k: requests[k] for k in keys[i:i + size]} for i in range(0, len(keys), size)]


def assemble_rounds() -> list:
    """Rounds from every usable draft (the last reply per key wins)."""
    drafts = {}
    for r in read_jsonl(WORK / "drafts.jsonl"):
        drafts[r["draft_key"]] = r
    out, dial_steps = [], {}
    for key, d in drafts.items():
        if d["error"] or not d["reply"] or not d["meta"]:
            continue
        d = {**d, "reply": llm.repair_value(d["reply"])}
        m = d["meta"]
        if m["mode"] == "when":
            if not d["reply"].get("usable"):
                continue
            out.append(rounds.when_round(m["page"], d["reply"], model=d["model"], drafted_at=d["drafted_at"]))
        elif m["mode"] == "same":
            if not d["reply"].get("usable"):
                continue
            out.append(rounds.same_round(m["pair"], m["a"], m["b"], d["reply"], model=d["model"], drafted_at=d["drafted_at"]))
        elif m["mode"] == "dial":
            dial_steps.setdefault(m["question_id"], []).append((m, d))
    pools = {e["question"]["id"]: e for e in (read_json(WORK / "dial_pools.json") or [])}
    for qid, steps in dial_steps.items():
        entry = pools[qid]
        by_ref = {p["ref"]: p for p in entry["pool"]}
        epochs = [{"year": m["year"], "reply": d["reply"], "pages": [by_ref[r] for r in m["pages"]]}
                  for m, d in sorted(steps, key=lambda md: md[0]["year"])]
        model = steps[0][1]["model"]
        out.append(rounds.dial_round(entry["question"], entry["pool"], epochs, model=model,
                                     drafted_at=max(d["drafted_at"] for _, d in steps), extra=entry["extra"]))
    return sorted(out, key=lambda r: r["id"])


# --- check ----------------------------------------------------------------------------------------

def cmd_check(args, s: settings.Settings) -> int:
    load_env()
    corpora = Corpora()
    checked = []
    for rnd in assemble_rounds():
        reasons = deck_mod.check_round(rnd, corpora, s.care)
        rnd["checks"] = {"builder_version": BUILDER_VERSION, "refusals": reasons, "checked_at": now(),
                         "fingerprint": deck_mod.round_fingerprint(rnd)}
        rnd["care_flags"] = [r[5:] for r in reasons if r.startswith("care:")]
        rnd["status"] = "refused" if reasons else "draft"
        checked.append(rnd)
    write_json(WORK / "checked.json", checked)
    by_mode = {}
    for r in checked:
        key = (r["mode"], r["status"])
        by_mode[key] = by_mode.get(key, 0) + 1
    print(json.dumps({f"{m}:{st}": n for (m, st), n in sorted(by_mode.items())}, indent=1))
    return 0


# --- panel and review -----------------------------------------------------------------------------

def _kept(checked: list) -> list:
    return [r for r in checked if r["status"] != "refused"]


def cmd_panel(args, s: settings.Settings) -> int:
    load_env()
    checked = read_json(WORK / "checked.json") or []
    cfg = judges.load_panel()
    writer_like = [{"writer_model": s.writer}]
    conflicts = judges.writer_conflicts(judges.PanelConfig(judges=cfg.judges, escalation=cfg.judges[0], candidates=(),
                                                           specs=cfg.specs), writer_like)
    if conflicts:
        print(f"refused: panel judges {conflicts} wrote these rounds")
        return 1
    ledger = ledger_for(s)
    done = {(r["round_id"], r["judge"], r["fingerprint"]) for r in read_jsonl(WORK / "panel.jsonl")} \
        if (WORK / "panel.jsonl").exists() else set()
    todo = [r for r in _kept(checked)][: args.limit or None]
    try:
        for name in cfg.judges:
            spec = cfg.specs[name]
            pending = [r for r in todo if (r["id"], name, r["checks"]["fingerprint"]) not in done]
            if not pending:
                continue
            print(f"[{name}] {len(pending)} rounds")
            if spec.provider == "anthropic":
                reqs = {r["id"]: llm.anthropic_request(spec.model, prompts.CHECK_SYSTEM, prompts.round_for_check(r),
                                                       prompts.CHECK_SCHEMA, max_tokens=spec.max_tokens, effort=spec.effort)
                        for r in pending}
                results = llm.run_anthropic_batch(reqs, ledger, args.run, args.cap, WORK / f"batch_{args.run}_{name}.json",
                                                  what=f"panel {name}")
            else:
                reqs = {r["id"]: (prompts.CHECK_SYSTEM, prompts.round_for_check(r)) for r in pending}
                results = llm.run_workers_ai_many(spec, reqs, prompts.CHECK_SCHEMA, ledger, args.run, args.cap,
                                                  gateway=cfg.workers_ai_gateway)
            fp = {r["id"]: r["checks"]["fingerprint"] for r in pending}
            for rid, res in results.items():
                append_jsonl(WORK / "panel.jsonl", {"round_id": rid, "judge": name, "family": spec.family,
                                                    "fingerprint": fp[rid], "prompt_version": prompts.CHECK_VERSION,
                                                    "calibrated": False, "at": now(), **res})
    except BudgetExceeded as exc:
        print(f"STOPPED: {exc}")
        return 2
    print(f"spent ${ledger.totals(args.run).spent:.4f} this run; phase ${ledger.totals().spent:.4f}")
    return 0


def callable_reviewer(s: settings.Settings) -> str:
    import anthropic
    client = anthropic.Anthropic()
    for model in s.reviewers:
        try:
            client.models.retrieve(model)
            return model
        except anthropic.NotFoundError:
            continue
    raise RuntimeError(f"none of the reviewer models {s.reviewers} is available to this account")


def cmd_review(args, s: settings.Settings) -> int:
    load_env()
    checked = read_json(WORK / "checked.json") or []
    model = args.model or callable_reviewer(s)
    ledger = ledger_for(s)
    done = {(r["round_id"], r["fingerprint"]) for r in read_jsonl(WORK / "review.jsonl")} \
        if (WORK / "review.jsonl").exists() else set()
    pending = [r for r in _kept(checked) if (r["id"], r["checks"]["fingerprint"]) not in done][: args.limit or None]
    if args.mode:
        pending = [r for r in pending if r["mode"] == args.mode]
    if not pending:
        print("nothing to review")
        return 0
    reqs = {r["id"]: llm.anthropic_request(model, prompts.REVIEW_SYSTEM, prompts.round_for_check(r), prompts.REVIEW_SCHEMA,
                                           max_tokens=args.max_tokens, effort=s.reviewer_effort) for r in pending}
    print(f"reviewing {len(reqs)} with {model} (run {args.run}, cap ${args.cap:.2f})")
    try:
        results = llm.run_anthropic_batch(reqs, ledger, args.run, args.cap, WORK / f"batch_{args.run}.json",
                                          what=f"review {model}")
    except BudgetExceeded as exc:
        print(f"STOPPED: {exc}")
        return 2
    fp = {r["id"]: r["checks"]["fingerprint"] for r in pending}
    for rid, res in results.items():
        append_jsonl(WORK / "review.jsonl", {"round_id": rid, "fingerprint": fp[rid], "prompt_version": prompts.REVIEW_VERSION,
                                             "at": now(), **res})
    print(f"spent ${ledger.totals(args.run).spent:.4f} this run; phase ${ledger.totals().spent:.4f}")
    return 0


# --- decide ---------------------------------------------------------------------------------------

def latest(path: Path, key) -> dict:
    out = {}
    if path.exists():
        for r in read_jsonl(path):
            out[key(r)] = r
    return out


def model_flags(rnd: dict, panel: dict, review: dict, panel_names: tuple) -> list:
    """Why a person must look at this round (empty when the panel and the reviewer pass it)."""
    fp = rnd["checks"]["fingerprint"]
    reasons = []
    for name in panel_names:
        rec = panel.get((rnd["id"], name, fp))
        if rec is None or rec.get("error") or not rec.get("reply"):
            reasons.append(f"panel:{name}:missing")
            continue
        v = rec["reply"]
        for check in ("supports", "answer_correct", "fair_to_visitor"):
            if v.get(check) != "pass":
                reasons.append(f"panel:{name}:{check}:{v.get(check)}")
        if v.get("needs_person"):
            reasons.append(f"panel:{name}:needs_person")
    rec = review.get((rnd["id"], fp))
    if rec is None or rec.get("error") or not rec.get("reply"):
        reasons.append("review:missing")
    else:
        v = rec["reply"]
        for check in ("supports", "answer_correct", "fair_to_visitor", "french_ok", "year_is_publication"):
            if v.get(check) != "pass":
                reasons.append(f"review:{check}:{v.get(check)}")
        if v.get("needs_person"):
            reasons.append("review:needs_person")
    return reasons


def author_decisions() -> dict:
    """Jake's decisions by round id; the last one for a round wins. Each names the fingerprint of
    the round he read, so a round that changed since needs reading again."""
    return latest(AUTHOR_REVIEWS, lambda r: r["round_id"])


def cmd_decide(args, s: settings.Settings) -> int:
    checked = read_json(WORK / "checked.json") or []
    panel = latest(WORK / "panel.jsonl", lambda r: (r["round_id"], r["judge"], r["fingerprint"]))
    review = latest(WORK / "review.jsonl", lambda r: (r["round_id"], r["fingerprint"]))
    authors = author_decisions()
    names = judges.load_panel().judges
    decided = []
    for rnd in checked:
        rnd = dict(rnd)
        if rnd["status"] == "refused":
            decided.append(rnd)
            continue
        fp = rnd["checks"]["fingerprint"]
        flags = model_flags(rnd, panel, review, names)
        rnd["review"] = {
            "panel": {n: (panel.get((rnd["id"], n, fp)) or {}).get("reply") for n in names},
            "panel_calibrated": False,
            "panel_prompt_version": prompts.CHECK_VERSION,
            "reviewer": {"model": (review.get((rnd["id"], fp)) or {}).get("model"),
                         "verdicts": (review.get((rnd["id"], fp)) or {}).get("reply"),
                         "prompt_version": prompts.REVIEW_VERSION,
                         "date": ((review.get((rnd["id"], fp)) or {}).get("at") or "")[:10]},
            "flags": flags,
            "author": None,
        }
        rnd["status"] = "flagged" if flags else "model-reviewed"
        decision = authors.get(rnd["id"])
        if decision and decision.get("fingerprint") == fp:
            rnd["review"]["author"] = {k: decision.get(k) for k in ("decision", "date", "notes", "reviewer")}
            if decision["decision"] == "approve":
                rnd["status"] = "author-reviewed"
                if decision.get("explanation"):
                    rnd["explanation"] = decision["explanation"]
                    rnd["explanation_status"] = "author-edited"
                    rnd["provenance"]["edits"].append({"date": decision["date"], "by": decision.get("reviewer", "Jake"),
                                                       "field": "explanation", "note": "edited in review"})
                else:
                    rnd["explanation_status"] = "author-reviewed"
            elif decision["decision"] == "reject":
                rnd["status"] = "author-rejected"
        decided.append(rnd)
    write_json(WORK / "decided.json", decided)
    counts = {}
    for r in decided:
        counts[f"{r['mode']}:{r['status']}"] = counts.get(f"{r['mode']}:{r['status']}", 0) + 1
    print(json.dumps(dict(sorted(counts.items())), indent=1))
    return 0


# --- choose and build -----------------------------------------------------------------------------

def choose(decided: list, s: settings.Settings) -> list:
    """The starter deck's rounds: publishable rounds only, Same or Not? balanced over the four
    answers, When Was This? spread over decades, every Time Dial question that passed."""
    ok = [r for r in decided if r["status"] in deck_mod.PUBLISHABLE]
    same = [r for r in ok if r["mode"] == "same_or_not"]
    by_answer = {}
    for r in sorted(same, key=lambda r: (r["status"] != "author-reviewed", r["id"])):
        by_answer.setdefault(r["play"]["answer"], []).append(r)
    chosen_same = []
    while len(chosen_same) < s.same_or_not_rounds and any(by_answer.values()):
        for answer in deck_mod.SAME_OR_NOT_CHOICES:
            if by_answer.get(answer) and len(chosen_same) < s.same_or_not_rounds:
                chosen_same.append(by_answer[answer].pop(0))
    # Level 1 teaches the lesson the Alberta story taught: two pages that look comparable count
    # different things. It is the first not_comparable round; the rest are level 2.
    level_one = next((r for r in chosen_same if r["play"]["answer"] == "not_comparable"), None)
    for r in chosen_same:
        r["level"] = 1 if r is level_one else 2
    chosen_same.sort(key=lambda r: (r["level"], r["id"]))
    when = [r for r in ok if r["mode"] == "when_was_this"]
    by_decade = {}
    for r in sorted(when, key=lambda r: (r["status"] != "author-reviewed", r["id"])):
        by_decade.setdefault(r["play"]["year"] // 10 * 10, []).append(r)
    chosen_when = []
    while len(chosen_when) < s.when_was_this_cards and any(by_decade.values()):
        for decade in sorted(by_decade):
            if by_decade[decade] and len(chosen_when) < s.when_was_this_cards:
                chosen_when.append(by_decade[decade].pop(0))
    dial = [r for r in ok if r["mode"] == "time_dial"][: s.time_dial_questions[1]]
    return chosen_same + sorted(chosen_when, key=lambda r: r["id"]) + dial


def cmd_build(args, s: settings.Settings) -> int:
    decided = read_json(WORK / "decided.json")
    if decided is None:
        print("run `decide` first")
        return 1
    chosen = choose(decided, s)
    from archive_debugger.qr import qr_path
    for rnd in chosen:
        for page in rnd["pages"]:
            size, path = qr_path(page["details_url"])
            page["qr"] = {"size": size, "path": path}
    grid = read_json(WORK / "gaphunt.json")
    summary = {"collections": list(s.collections), "dial": [s.dial_first_year, s.dial_last_year],
               "idle_reset_seconds": s.idle_reset_seconds, "offline_image_cache": s.offline_image_cache,
               "panel_calibrated": False}
    doc = deck_mod.deck_document(args.deck_id, now(), BUILDER_VERSION, chosen, grid, summary)
    PUBLISHED.mkdir(parents=True, exist_ok=True)
    write_json(PUBLISHED / "deck.json", doc)
    rejected = [{"id": r["id"], "mode": r["mode"], "status": r["status"],
                 "reasons": r["checks"]["refusals"] or (r.get("review") or {}).get("flags") or []}
                for r in decided if r["status"] in ("refused", "author-rejected")]
    write_json(WORK / "rejected.json", rejected)
    short = {m: doc["counts"][m] for m in deck_mod.MODES}
    want = {"same_or_not": s.same_or_not_rounds, "when_was_this": s.when_was_this_cards,
            "time_dial": s.time_dial_questions[0]}
    print(f"deck {args.deck_id}: {short}; rejected {len(rejected)} -> {PUBLISHED / 'deck.json'}")
    missing = {m: want[m] - short[m] for m in want if short[m] < want[m]}
    if missing:
        print(f"SHORT of the starter sizes: {missing}")
    return 0


def cmd_gaphunt(args, s: settings.Settings) -> int:
    load_env()
    corpora = Corpora()
    counts_file = REPO / "exhibit" / "decks" / "starter" / "catalogue_counts.json"
    grid = gaphunt.build_grid(corpora, s, read_json(counts_file))
    write_json(WORK / "gaphunt.json", grid)
    print(f"gap hunt: {len(grid['cells'])} cells, {len(grid['jurisdictions'])} jurisdictions, decades {grid['decades']}")
    return 0


def cmd_status(args, s: settings.Settings) -> int:
    ledger = ledger_for(s)
    t = ledger.totals()
    print(f"spent ${t.spent:.4f}, reserved ${t.reserved:.4f}, cap ${s.phase_cap_usd:.2f}; by provider {t.by_provider}")
    for name in ("candidates.json", "drafts.jsonl", "checked.json", "panel.jsonl", "review.jsonl", "decided.json"):
        path = WORK / name
        print(f"  {name}: {'present' if path.exists() else 'absent'}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("mine")
    m.add_argument("--config", default="mining.toml", help="a mining file in exhibit/decks/starter/")
    sub.add_parser("pools")
    d = sub.add_parser("draft")
    d.add_argument("--run", required=True)
    d.add_argument("--cap", type=float, required=True)
    d.add_argument("--limit", type=int, default=0)
    d.add_argument("--modes", default="when,same,dial")
    d.add_argument("--chunk", type=int, default=50)
    d.add_argument("--redo-refused", action="store_true", help="draft again what the builder refused for an off-page quote")
    sub.add_parser("check")
    p = sub.add_parser("panel")
    p.add_argument("--run", required=True)
    p.add_argument("--cap", type=float, required=True)
    p.add_argument("--limit", type=int, default=0)
    r = sub.add_parser("review")
    r.add_argument("--run", required=True)
    r.add_argument("--cap", type=float, required=True)
    r.add_argument("--limit", type=int, default=0)
    r.add_argument("--model", default=None)
    r.add_argument("--mode", default=None)
    r.add_argument("--max-tokens", type=int, default=8000)
    sub.add_parser("decide")
    sub.add_parser("gaphunt")
    b = sub.add_parser("build")
    b.add_argument("--deck-id", required=True)
    sub.add_parser("status")
    args = ap.parse_args(argv)
    load_env()
    s = settings.load()
    return {"mine": cmd_mine, "pools": cmd_pools, "draft": cmd_draft, "check": cmd_check, "panel": cmd_panel, "review": cmd_review,
            "decide": cmd_decide, "gaphunt": cmd_gaphunt, "build": cmd_build, "status": cmd_status}[args.cmd](args, s)


if __name__ == "__main__":
    sys.exit(main())
