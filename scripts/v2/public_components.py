"""Small, seeded subsets of three public datasets, used only to choose parts (Phase 2 Part C).

    python scripts/v2/public_components.py
    python scripts/v2/public_components.py --only miracl_fr --seed 20261101

These are component checks, not our benchmark. They help pick an embedder (French retrieval),
an abstention policy (questions that should not be answered) and OCR robustness (questions over
raw newspaper OCR). Nothing here is ever reported as a measure of how well the archive answers.

Subsets written under reports/v2/public_components/<name>/ (gitignored, never committed):

  miracl_fr             MIRACL French dev topics: 300 queries drawn with the seed, every judged
                        passage for them (relevant and judged non-relevant), fetched one batch at
                        a time through the Hugging Face datasets-server filter endpoint, so the
                        1.9 GB corpus is never downloaded.
  abstentionbench       AbstentionBench-style items taken from the original sources of the
                        AbstentionBench sub-datasets whose own licences permit it. The
                        AbstentionBench package itself is CC BY-NC 4.0, so none of its files
                        (prompts, subsampling indices, category maps) are downloaded; its refusal
                        is recorded in the manifest with every other refused sub-dataset.
  chroniclingamericaqa  ChroniclingAmericaQA test split: seeded blocks of consecutive rows read
                        through datasets-server, with the raw OCR next to the corrected text.

Every subset gets a manifest.json: source URLs, the revision read at fetch time, the licence as
the source states it, the decision taken on it, the seed, counts, and the sha256 and size of every
file written. A source whose licence is missing, non-commercial, no-derivatives, off the allow
list, or different from the value reviewed when this script was written is refused: nothing is
downloaded from it and the refusal is written to the manifest instead.

Requests are polite: one at a time, an identified user agent with a contact address, a pause
after each network call, retries with backoff on timeouts, resets, 5xx, 408 and 429 (and on the
datasets-server's own "try again later" replies), and every reply cached under
reports/v2/raw/public_components/ so a rerun makes no network calls. No direct file over 200 MB is
ever fetched. Standard library only.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
OUT = REPO / "reports" / "v2" / "public_components"
CACHE = REPO / "reports" / "v2" / "raw" / "public_components"
USER_AGENT = "archive-argues-research/1.0 (+https://archiveargues.org; hello@archiveargues.org)"
DEFAULT_SEED = 20261101
MAX_FILE_BYTES = 200 * 1024 * 1024
PURPOSE = ("Component check used only to choose parts (embedder, abstention policy, OCR "
           "robustness). Not our benchmark; never reported as archive accuracy.")

HF_API = "https://huggingface.co/api/datasets/"
HF_FILE = "https://huggingface.co/datasets/{repo}/resolve/{rev}/{path}"
DS_SERVER = "https://datasets-server.huggingface.co/"
GH_API = "https://api.github.com/repos/"
GH_RAW = "https://raw.githubusercontent.com/{repo}/{rev}/{path}"

# Licences a subset may be built from. Everything else is refused.
ALLOWED_LICENCES = {"mit", "apache-2.0", "cc-by-4.0", "cc-by-sa-4.0", "cc-by-sa-3.0", "cc0-1.0",
                    "odc-by", "bsd-2-clause", "bsd-3-clause"}
NO_GRANT = {"", "none", "other", "unknown", "noassertion", "unlicensed"}

RETRY_STATUS = {408, 429, 500, 502, 503, 504}
TRANSIENT_SERVER_TEXT = ("try again later", "is loading", "temporary", "unexpected error",
                         "timed out")


class FetchError(RuntimeError):
    pass


def default_transport(url: str, timeout: float = 60.0) -> tuple[int, bytes]:
    """The only function here that touches the network. Tests replace it."""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT,
                                                   "Accept-Encoding": "identity"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as error:
        return error.code, error.read() or b""


class Fetcher:
    """One request at a time, cached on disk, with one retry rule for every source."""

    def __init__(self, transport=default_transport, sleeper=time.sleep, cache_dir: Path | None = CACHE,
                 pause: float = 1.0, retries: int = 6, backoff: float = 3.0):
        self.transport = transport
        self.sleeper = sleeper
        self.cache_dir = cache_dir
        self.pause = pause
        self.retries = retries
        self.backoff = backoff
        self.network_calls = 0
        self.network_bytes = 0
        self.cached_bytes = 0

    def _cache_path(self, url: str) -> Path | None:
        if self.cache_dir is None:
            return None
        return self.cache_dir / (hashlib.sha256(url.encode("utf-8")).hexdigest() + ".bin")

    def get(self, url: str) -> bytes:
        cached = self._cache_path(url)
        if cached is not None and cached.exists():
            body = cached.read_bytes()
            self.cached_bytes += len(body)
            return body
        last_problem = ""
        for attempt in range(self.retries + 1):
            if attempt:
                self.sleeper(self.backoff * (2 ** (attempt - 1)))
            try:
                status, body = self.transport(url)
            except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as error:
                last_problem = f"network error: {error}"
                continue
            finally:
                self.network_calls += 1
                self.sleeper(self.pause)
            if status in RETRY_STATUS:
                last_problem = f"HTTP {status}"
                continue
            if status >= 400:
                raise FetchError(f"HTTP {status} for {url}: {body[:200]!r}")
            if url.startswith(DS_SERVER) and _transient_server_reply(body):
                last_problem = f"datasets-server said: {body[:160]!r}"
                continue
            self.network_bytes += len(body)
            if cached is not None:
                cached.parent.mkdir(parents=True, exist_ok=True)
                cached.write_bytes(body)
            return body
        raise FetchError(f"gave up on {url} after {self.retries + 1} tries ({last_problem})")

    def get_json(self, url: str):
        return json.loads(self.get(url).decode("utf-8"))


def _transient_server_reply(body: bytes) -> bool:
    if not body.startswith(b"{\"error\""):
        return False
    try:
        message = str(json.loads(body.decode("utf-8")).get("error", "")).lower()
    except (ValueError, UnicodeDecodeError):
        return False
    return any(text in message for text in TRANSIENT_SERVER_TEXT)


# ---------------------------------------------------------------- licences and revisions


def normalise_licence(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        value = [value]
    return [str(item).strip().lower() for item in value]


def licence_decision(declared: list[str], reviewed: list[str] | None = None) -> tuple[str, str]:
    """('permitted' | 'refused', reason). `reviewed` is the value read when this script was
    written; a source whose licence has changed since is refused until someone looks again."""
    if not declared or any(item in NO_GRANT for item in declared):
        return "refused", "no licence grant found at the source"
    for item in declared:
        parts = set(re.split(r"[-_. ]", item))
        if "nc" in parts or "noncommercial" in item or "non-commercial" in item:
            return "refused", f"non-commercial licence ({item})"
        if "nd" in parts or "noderivatives" in item:
            return "refused", f"no-derivatives licence ({item})"
    off_list = [item for item in declared if item not in ALLOWED_LICENCES]
    if off_list:
        return "refused", f"licence not on the allow list ({', '.join(off_list)})"
    if reviewed is not None and sorted(declared) != sorted(reviewed):
        return "refused", (f"licence reads {declared} but {reviewed} was reviewed; "
                           "review it again before use")
    return "permitted", "licence permits use and redistribution"


def hf_dataset_info(fetcher: Fetcher, repo: str) -> dict:
    info = fetcher.get_json(HF_API + repo + "?blobs=true")
    card = info.get("cardData") or {}
    return {"repo": repo, "url": "https://huggingface.co/datasets/" + repo, "revision": info.get("sha"),
            "licence": normalise_licence(card.get("license")), "licence_evidence": "dataset card license field",
            "gated": info.get("gated"),
            "file_sizes": {item["rfilename"]: item.get("size") for item in info.get("siblings", [])}}


def gh_repo_info(fetcher: Fetcher, repo: str) -> dict:
    info = fetcher.get_json(GH_API + repo)
    branch = info.get("default_branch", "main")
    commit = fetcher.get_json(GH_API + repo + "/commits/" + branch)
    licence = (info.get("license") or {}).get("spdx_id")
    return {"repo": repo, "url": "https://github.com/" + repo, "revision": commit.get("sha"), "branch": branch,
            "licence": normalise_licence(licence), "licence_evidence": "GitHub licence detection (LICENSE file)"}


def source_record(info: dict, reviewed: list[str], role: str) -> dict:
    decision, reason = licence_decision(info["licence"], reviewed)
    record = {key: info[key] for key in ("repo", "url", "revision", "licence", "licence_evidence") if key in info}
    record.update({"role": role, "licence_reviewed": reviewed, "decision": decision, "reason": reason})
    return record


def check_file_size(size, label: str):
    if size is None:
        raise FetchError(f"{label}: size unknown, not fetched")
    if size > MAX_FILE_BYTES:
        raise FetchError(f"{label}: {size} bytes is over the {MAX_FILE_BYTES} byte limit, not fetched")


# ---------------------------------------------------------------- datasets-server helpers


def ds_url(endpoint: str, **params) -> str:
    return DS_SERVER + endpoint + "?" + urllib.parse.urlencode(params)


def ds_num_rows(fetcher: Fetcher, dataset: str, config: str, split: str) -> int:
    size = fetcher.get_json(ds_url("size", dataset=dataset, config=config))
    for row in size["size"]["splits"]:
        if row["split"] == split:
            return int(row["num_rows"])
    raise FetchError(f"{dataset}/{config} has no split {split}")


def ds_rows(fetcher: Fetcher, dataset: str, config: str, split: str, offset: int, length: int) -> list[dict]:
    reply = fetcher.get_json(ds_url("rows", dataset=dataset, config=config, split=split,
                                    offset=offset, length=length))
    return reply["rows"]


def seeded_blocks(rng: random.Random, total_rows: int, block: int, count: int) -> list[int]:
    """Start offsets of `count` non-overlapping blocks of `block` consecutive rows."""
    starts = rng.sample(range(total_rows // block), count)
    return sorted(start * block for start in starts)


# ---------------------------------------------------------------- writing


def write_jsonl(path: Path, rows: list[dict]) -> dict:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    return file_entry(path, len(rows))


def file_entry(path: Path, rows: int | None = None) -> dict:
    data = path.read_bytes()
    entry = {"path": path.name, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
    if rows is not None:
        entry["rows"] = rows
    return entry


def write_manifest(out_dir: Path, manifest: dict) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "manifest.json"
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(manifest, indent=2, ensure_ascii=True, sort_keys=False) + "\n")
    return path


def base_manifest(name: str, seed: int) -> dict:
    return {"name": name, "purpose": PURPOSE, "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "script": "scripts/v2/public_components.py", "user_agent": USER_AGENT, "seed": seed,
            "status": None, "sources": [], "refused": [], "counts": {}, "files": [], "notes": []}


def finish(fetcher: Fetcher, manifest: dict, start_calls: int, start_bytes: int) -> None:
    manifest["network"] = {"calls": fetcher.network_calls - start_calls,
                           "bytes_fetched": fetcher.network_bytes - start_bytes}


# ---------------------------------------------------------------- MIRACL French

MIRACL_TOPICS = "miracl/miracl"
MIRACL_CORPUS = "miracl/miracl-corpus"
MIRACL_TOPICS_FILE = "miracl-v1.0-fr/topics/topics.miracl-v1.0-fr-dev.tsv"
MIRACL_QRELS_FILE = "miracl-v1.0-fr/qrels/qrels.miracl-v1.0-fr-dev.tsv"
DOCID = re.compile(r"^[0-9]+#[0-9]+$")


def build_miracl_fr(fetcher: Fetcher, out_dir: Path, seed: int, queries: int = 300, batch: int = 100) -> dict:
    manifest = base_manifest("miracl_fr", seed)
    start_calls, start_bytes = fetcher.network_calls, fetcher.network_bytes
    topics_info = hf_dataset_info(fetcher, MIRACL_TOPICS)
    corpus_info = hf_dataset_info(fetcher, MIRACL_CORPUS)
    topics_source = source_record(topics_info, ["apache-2.0"], "French dev topics and relevance judgments")
    corpus_source = source_record(corpus_info, ["apache-2.0"], "French Wikipedia passages")
    corpus_source["content_licence_note"] = ("Passages are French Wikipedia text, which Wikipedia "
                                            "licenses CC BY-SA; attribution and share-alike apply to the text.")
    manifest["sources"] = [topics_source, corpus_source]
    if any(source["decision"] == "refused" for source in manifest["sources"]):
        manifest["status"] = "refused"
        manifest["refused"] = [s for s in manifest["sources"] if s["decision"] == "refused"]
        finish(fetcher, manifest, start_calls, start_bytes)
        write_manifest(out_dir, manifest)
        return manifest

    revision = topics_info["revision"]
    texts = {}
    for path in (MIRACL_TOPICS_FILE, MIRACL_QRELS_FILE):
        check_file_size(topics_info["file_sizes"].get(path), path)
        url = HF_FILE.format(repo=MIRACL_TOPICS, rev=revision, path=path)
        texts[path] = fetcher.get(url).decode("utf-8")
        topics_source.setdefault("files_read", []).append(url)

    all_topics = {}
    for line in texts[MIRACL_TOPICS_FILE].splitlines():
        if line.strip():
            qid, query = line.split("\t", 1)
            all_topics[qid.strip()] = query.strip()
    judgments: dict[str, list[tuple[str, int]]] = {}
    for line in texts[MIRACL_QRELS_FILE].splitlines():
        parts = line.split()
        if len(parts) == 4:
            judgments.setdefault(parts[0], []).append((parts[2], int(parts[3])))

    eligible = sorted(qid for qid in all_topics if qid in judgments)
    rng = random.Random(seed)
    chosen = sorted(rng.sample(eligible, min(queries, len(eligible))))
    query_rows = [{"query_id": qid, "query": all_topics[qid]} for qid in chosen]
    qrel_rows = [{"query_id": qid, "docid": docid, "relevance": relevance}
                 for qid in chosen for docid, relevance in judgments[qid]]

    wanted = sorted({row["docid"] for row in qrel_rows})
    bad_ids = [docid for docid in wanted if not DOCID.match(docid)]
    if bad_ids:
        raise FetchError(f"unexpected docid shapes in the judgments, not sent to the server: {bad_ids[:5]}")
    passages: dict[str, dict] = {}
    failed_batches = 0
    partial_index = False
    for start in range(0, len(wanted), batch):
        ids = wanted[start:start + batch]
        where = " OR ".join(f"\"docid\"='{docid}'" for docid in ids)
        offset = 0
        while True:
            try:
                reply = fetcher.get_json(ds_url("filter", dataset=MIRACL_CORPUS, config="fr", split="train",
                                                where=where, offset=offset, length=100))
            except FetchError as error:
                # Successful replies are cached, so a rerun fetches only the batches that failed.
                failed_batches += 1
                print(f"miracl_fr: batch at {start} not fetched this run: {error}")
                break
            partial_index = partial_index or bool(reply.get("partial"))
            for item in reply.get("rows", []):
                row = item["row"]
                if row["docid"] in ids and row["docid"] not in passages:
                    passages[row["docid"]] = {"docid": row["docid"], "title": row["title"], "text": row["text"],
                                              "truncated": bool(item.get("truncated_cells"))}
            offset += 100
            if offset >= int(reply.get("num_rows_total", 0)):
                break
    corpus_source["files_read"] = [DS_SERVER + "filter (dataset=miracl/miracl-corpus, config=fr, split=train, "
                                   f"{batch} docids per request)"]
    corpus_source["revision_note"] = ("datasets-server reads its parquet conversion of the main branch; "
                                      "revision is the hub sha read at fetch time")
    missing = [docid for docid in wanted if docid not in passages]
    passage_rows = [passages[docid] for docid in wanted if docid in passages]

    manifest["files"] = [write_jsonl(out_dir / "queries.jsonl", query_rows),
                         write_jsonl(out_dir / "qrels.jsonl", qrel_rows),
                         write_jsonl(out_dir / "passages.jsonl", passage_rows)]
    manifest["counts"] = {"dev_queries_available": len(eligible), "queries": len(query_rows),
                          "judgments": len(qrel_rows),
                          "relevant_judgments": sum(1 for row in qrel_rows if row["relevance"] > 0),
                          "passages_wanted": len(wanted), "passages_written": len(passage_rows),
                          "passages_missing": len(missing),
                          "passages_truncated": sum(1 for row in passage_rows if row["truncated"]),
                          "filter_batches_failed": failed_batches}
    manifest["missing_docids"] = missing
    manifest["filter_index_partial"] = partial_index
    manifest["notes"] = ["The candidate pool is every passage a MIRACL annotator judged for the chosen queries, "
                         "relevant or not, so retrieval over it is a reranking-style check, not a full-corpus one.",
                         "Query sample: random.Random(seed).sample over the sorted dev topic ids that have judgments.",
                         "filter_index_partial true means datasets-server reported that its search index covers "
                         "only part of the corpus, so a missing passage may exist in the corpus but not in the index. "
                         "Missing docids are listed; a rerun retries only failed batches (replies are cached)."]
    manifest["status"] = "complete" if not missing else "partial"
    finish(fetcher, manifest, start_calls, start_bytes)
    write_manifest(out_dir, manifest)
    return manifest


# ---------------------------------------------------------------- AbstentionBench-style items

ABSTENTIONBENCH = "facebook/AbstentionBench"

# Sub-datasets reviewed and refused, with the evidence read when this script was written. The ones
# with a `check` are re-read live so the manifest quotes what the source says today.
ABSTENTION_REFUSALS = [
    {"name": "AbstentionBench package (prompts, subsampling indices, category maps)",
     "check": ("hf", ABSTENTIONBENCH), "reviewed": ["cc-by-nc-4.0"]},
    {"name": "FalseQA (thunlp/FalseQA, test.csv)", "check": ("gh", "thunlp/FalseQA"), "reviewed": [],
     "extra": "The repository has no LICENSE file, so no reuse grant exists."},
    {"name": "SituatedQA geo (mikejqzhang/SituatedQA)", "check": ("gh", "mikejqzhang/SituatedQA"), "reviewed": [],
     "extra": ("The authors' repository has no LICENSE file. A third-party Hugging Face mirror "
               "(siyue/SituatedQA) labels it MIT, but its loader downloads the authors' files, and "
               "a mirror's label cannot grant rights the authors did not.")},
    {"name": "CoCoNot (allenai/coconot)", "check": None, "reviewed": [],
     "licence": ["https://allenai.org/licenses/impact-lr", "odc-by"],
     "extra": ("The dataset card gives two licences: 'License: https://allenai.org/licenses/impact-lr' "
               "and 'CoCoNot is made available under the ODC-BY requiring the user to follow the "
               "licenses of the subsequent parts.' Refused until the conflict is resolved.")},
]

ABSTENTION_NOT_SELECTED = [
    ("GPQA (Idavidrein/gpqa)", "gated, and its authors ask that examples not be reshared in plain text"),
    ("GSM8K and MMLU abstain variants", "the abstain versions are built by AbstentionBench code, which is CC BY-NC 4.0"),
    ("BBQ (nyu-mll/BBQ)", "social-bias probes; not relevant to archival questions and kept out on purpose"),
    ("MoralChoice", "moral scenarios; not relevant to archival questions"),
    ("ALCUNA, NQ and MuSiQue unanswerable sets, QAQA", "distributed as Google Drive archives; licences not reviewed"),
    ("MediQ, UMWP, WorldSense, BIG-Bench Hard disambiguation", "licences not reviewed for this subset"),
    ("QASPER (allenai/qasper)", "every item carries a full paper; no small subset path without the whole archive"),
]

SQUAD = "rajpurkar/squad_v2"
KUQ = "amayuelas/KUQ"
KUQ_FILE = "knowns_unknowns.jsonl"
BIGBENCH = "google/BIG-bench"
BIGBENCH_TASK = "bigbench/benchmark_tasks/known_unknowns/task.json"


def build_abstentionbench(fetcher: Fetcher, out_dir: Path, seed: int, squad_items: int = 150,
                          kuq_items: int = 150) -> dict:
    manifest = base_manifest("abstentionbench", seed)
    start_calls, start_bytes = fetcher.network_calls, fetcher.network_bytes
    rng = random.Random(seed)

    for refusal in ABSTENTION_REFUSALS:
        record = {"name": refusal["name"], "decision": "refused", "licence_reviewed": refusal["reviewed"]}
        if refusal["check"] is not None:
            kind, repo = refusal["check"]
            info = hf_dataset_info(fetcher, repo) if kind == "hf" else gh_repo_info(fetcher, repo)
            record.update({"url": info["url"], "revision": info["revision"], "licence": info["licence"],
                           "licence_evidence": info["licence_evidence"]})
            decision, reason = licence_decision(info["licence"], None)
            if decision == "permitted":
                reason = "licence now reads as permitted; still refused until reviewed again"
            record["reason"] = reason
        else:
            record.update({"licence": refusal["licence"], "reason": "conflicting licence statements"})
        if "extra" in refusal:
            record["evidence"] = refusal["extra"]
        manifest["refused"].append(record)
    manifest["not_selected"] = [{"name": name, "reason": reason} for name, reason in ABSTENTION_NOT_SELECTED]

    items: list[dict] = []

    # SQuAD 2.0 validation: unanswerable questions are the ones with no gold answer.
    squad_source = source_record(hf_dataset_info(fetcher, SQUAD), ["cc-by-sa-4.0"],
                                 "context-grounded questions, some unanswerable from the context")
    manifest["sources"].append(squad_source)
    if squad_source["decision"] == "permitted":
        total = ds_num_rows(fetcher, SQUAD, "squad_v2", "validation")
        block = 5
        for start in seeded_blocks(rng, total, block, squad_items // block):
            for item in ds_rows(fetcher, SQUAD, "squad_v2", "validation", start, block):
                row = item["row"]
                answers = sorted(set(row["answers"]["text"]))
                items.append({"source": "squad_v2", "source_id": row["id"], "row_idx": item["row_idx"],
                              "question": row["question"], "context": row["context"], "title": row["title"],
                              "should_abstain": not answers, "reference_answers": answers or None,
                              "category": "answer not in context" if not answers else "answerable from context",
                              "truncated": bool(item.get("truncated_cells"))})
        squad_source["files_read"] = [DS_SERVER + f"rows (config=squad_v2, split=validation, {squad_items // block} "
                                      f"seeded blocks of {block} rows out of {total})"]

    # KUQ: known and unknown questions, paired by the authors.
    kuq_info = hf_dataset_info(fetcher, KUQ)
    kuq_source = source_record(kuq_info, ["mit"], "known and unknown questions")
    manifest["sources"].append(kuq_source)
    if kuq_source["decision"] == "permitted":
        check_file_size(kuq_info["file_sizes"].get(KUQ_FILE), KUQ_FILE)
        url = HF_FILE.format(repo=KUQ, rev=kuq_info["revision"], path=KUQ_FILE)
        lines = [line for line in fetcher.get(url).decode("utf-8").splitlines() if line.strip()]
        kuq_source["files_read"] = [url]
        kuq_source["rows_available"] = len(lines)
        for index in sorted(rng.sample(range(len(lines)), min(kuq_items, len(lines)))):
            row = json.loads(lines[index])
            unknown = bool(row.get("unknown"))
            items.append({"source": "kuq", "source_id": f"{KUQ_FILE}:{index}", "question": row.get("question"),
                          "should_abstain": unknown, "reference_answers": None if unknown else row.get("answer"),
                          "uncertainty_sources": row.get("answer") if unknown else None,
                          "category": row.get("category"), "origin": row.get("source")})

    # BIG-bench known_unknowns: the whole task (46 items).
    bb_info = gh_repo_info(fetcher, BIGBENCH)
    bb_source = source_record(bb_info, ["apache-2.0"], "questions whose answer is known to be unknown")
    manifest["sources"].append(bb_source)
    if bb_source["decision"] == "permitted":
        url = GH_RAW.format(repo=BIGBENCH, rev=bb_info["revision"], path=BIGBENCH_TASK)
        task = json.loads(fetcher.get(url).decode("utf-8"))
        bb_source["files_read"] = [url]
        bb_source["canary"] = task.get("canary")
        for index, example in enumerate(task["examples"]):
            scores = example["target_scores"]
            abstain = scores.get("Unknown") == 1
            answers = [text for text, score in scores.items() if score == 1 and text != "Unknown"]
            items.append({"source": "bigbench_known_unknowns", "source_id": f"known_unknowns:{index}",
                          "question": example["input"], "should_abstain": abstain,
                          "reference_answers": None if abstain else answers, "category": "known unknown"})

    manifest["files"] = [write_jsonl(out_dir / "items.jsonl", items)]
    by_source: dict[str, dict] = {}
    for item in items:
        tally = by_source.setdefault(item["source"], {"items": 0, "should_abstain": 0})
        tally["items"] += 1
        tally["should_abstain"] += int(bool(item["should_abstain"]))
    manifest["counts"] = {"items": len(items), "should_abstain": sum(t["should_abstain"] for t in by_source.values()),
                          "by_source": by_source}
    manifest["notes"] = ["Items come from each sub-dataset's original source, not from the AbstentionBench "
                         "package, whose own files are CC BY-NC 4.0 and were not downloaded.",
                         "The answerable / should-abstain label is the one each source defines: SQuAD 2.0 "
                         "has no gold answer; KUQ marks unknown=true; BIG-bench scores 'Unknown' as correct.",
                         "BIG-bench asks that its data never appear in training corpora; the canary string "
                         "is kept in this manifest."]
    manifest["status"] = "complete" if items else "refused"
    finish(fetcher, manifest, start_calls, start_bytes)
    write_manifest(out_dir, manifest)
    return manifest


# ---------------------------------------------------------------- ChroniclingAmericaQA

CAQA = "Bhawna/ChroniclingAmericaQA"
CAQA_GITHUB = "DataScienceUIBK/ChroniclingAmericaQA"
CAQA_FIELDS = ("query_id", "question", "answer", "org_answer", "para_id", "context", "raw_ocr",
               "publication_date", "trans_que", "trans_ans", "url")


def build_chroniclingamericaqa(fetcher: Fetcher, out_dir: Path, seed: int, items: int = 300,
                               block: int = 10) -> dict:
    manifest = base_manifest("chroniclingamericaqa", seed)
    start_calls, start_bytes = fetcher.network_calls, fetcher.network_bytes
    hf_source = source_record(hf_dataset_info(fetcher, CAQA), ["mit"], "question-answer pairs over newspaper OCR")
    gh_source = source_record(gh_repo_info(fetcher, CAQA_GITHUB), ["mit"], "authors' code and data repository")
    hf_source["content_licence_note"] = ("Page text comes from the Library of Congress Chronicling America "
                                        "OCR of historical US newspapers.")
    manifest["sources"] = [hf_source, gh_source]
    if any(source["decision"] == "refused" for source in manifest["sources"]):
        manifest["status"] = "refused"
        manifest["refused"] = [s for s in manifest["sources"] if s["decision"] == "refused"]
        finish(fetcher, manifest, start_calls, start_bytes)
        write_manifest(out_dir, manifest)
        return manifest

    total = ds_num_rows(fetcher, CAQA, "default", "test")
    rng = random.Random(seed)
    rows = []
    for start in seeded_blocks(rng, total, block, items // block):
        for item in ds_rows(fetcher, CAQA, "default", "test", start, block):
            row = {field: item["row"].get(field) for field in CAQA_FIELDS}
            row["row_idx"] = item["row_idx"]
            row["truncated"] = bool(item.get("truncated_cells"))
            rows.append(row)
    hf_source["files_read"] = [DS_SERVER + f"rows (config=default, split=test, {items // block} seeded blocks "
                               f"of {block} rows out of {total})"]
    hf_source["revision_note"] = ("datasets-server reads its parquet conversion of the main branch; "
                                  "revision is the hub sha read at fetch time")
    manifest["files"] = [write_jsonl(out_dir / "items.jsonl", rows)]
    manifest["counts"] = {"test_rows_available": total, "items": len(rows),
                          "truncated": sum(1 for row in rows if row["truncated"]),
                          "with_raw_ocr": sum(1 for row in rows if row.get("raw_ocr"))}
    manifest["notes"] = ["Blocks of consecutive test rows at seeded offsets; consecutive rows often share a "
                         "newspaper page, so the 300 items cover fewer distinct pages.",
                         "`context` is the corrected paragraph the question was written from; `raw_ocr` is "
                         "the uncorrected OCR of the same paragraph, which is what the OCR check reads."]
    manifest["status"] = "complete" if rows else "empty"
    finish(fetcher, manifest, start_calls, start_bytes)
    write_manifest(out_dir, manifest)
    return manifest


# ---------------------------------------------------------------- command line

BUILDERS = {"miracl_fr": build_miracl_fr, "abstentionbench": build_abstentionbench,
            "chroniclingamericaqa": build_chroniclingamericaqa}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--only", choices=sorted(BUILDERS), action="append",
                        help="build only this subset (repeatable)")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--out", type=Path, default=OUT)
    parser.add_argument("--no-cache", action="store_true", help="ignore and do not write the reply cache")
    args = parser.parse_args(argv)

    fetcher = Fetcher(cache_dir=None if args.no_cache else CACHE)
    failures = 0
    for name in args.only or list(BUILDERS):
        try:
            manifest = BUILDERS[name](fetcher, args.out / name, args.seed)
        except FetchError as error:
            failures += 1
            print(f"{name}: FAILED: {error}")
            continue
        print(f"{name}: {manifest['status']} {json.dumps(manifest['counts'], sort_keys=True)}")
        for entry in manifest["files"]:
            print(f"  {entry['path']}: {entry['bytes']} bytes, sha256 {entry['sha256'][:16]}")
        for refusal in manifest["refused"]:
            print(f"  refused: {refusal.get('name') or refusal.get('repo')}: {refusal['reason']}")
    print(f"network calls {fetcher.network_calls}, bytes fetched {fetcher.network_bytes}, "
          f"bytes from cache {fetcher.cached_bytes}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
