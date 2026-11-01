"""Batch jobs: specs, stores, resumable and idempotent runs, manifests, and the embed, judge and ocr
jobs with their backends replaced. No test reaches a real host, a GPU or a model."""
from __future__ import annotations

import io
import json
import socket
from pathlib import Path

import numpy as np
import pytest

from archive_debugger.jobs import embed, judge, ocr, runner, spec as spec_mod, store as store_mod


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("a test tried to open a network connection")
    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)


def write_spec(tmp_path: Path, kind: str, extra: str = "") -> spec_mod.JobSpec:
    path = tmp_path / f"{kind}-t.toml"
    path.write_text(f"""
[job]
name = "{kind}-t"
kind = "{kind}"
code_version = "1"
[input]
prefix = "in/{kind}-t"
[output]
prefix = "jobs"
[model]
name = "m"
licence = "Apache-2.0"
[params]
index_spec = "config/jobs/index_spec.toml"
{extra}
[executor.local]
endpoint = "http://judge.example.test/v1"
model = "m-local"
""", encoding="utf-8")
    return spec_mod.load(str(path))


def put_units(store, spec, units):
    store.put(f"{spec.input_prefix}/{runner.UNITS}", "".join(json.dumps(u) + "\n" for u in units).encode())


def test_spec_requires_a_licence_and_known_kind(tmp_path):
    bad = tmp_path / "bad.toml"
    bad.write_text('[job]\nname="x"\nkind="embed"\ncode_version="1"\n[model]\nname="m"\n', encoding="utf-8")
    with pytest.raises(spec_mod.SpecError, match="licence"):
        spec_mod.load(str(bad))
    bad.write_text('[job]\nname="x"\nkind="train"\ncode_version="1"\n[model]\nlicence="MIT"\n', encoding="utf-8")
    with pytest.raises(spec_mod.SpecError, match="kind"):
        spec_mod.load(str(bad))


def test_build_key_changes_with_what_changes_the_output(tmp_path):
    s = write_spec(tmp_path, "embed")
    assert s.build_key("a") == s.build_key("a")
    assert s.build_key("a") != s.build_key("b")
    t = write_spec(tmp_path, "embed", "batch = 7")
    assert t.build_key("a") != s.build_key("a")


def test_local_store_refuses_unsafe_keys(tmp_path):
    st = store_mod.LocalStore(tmp_path)
    with pytest.raises(ValueError):
        st.put("../escape", b"x")
    meta = st.put("a/b.txt", b"hello")
    assert st.head("a/b.txt") == meta
    assert list(st.list("a")) == ["a/b.txt"]


def test_run_resumes_and_never_repeats_a_finished_unit(tmp_path):
    st = store_mod.LocalStore(tmp_path)
    s = write_spec(tmp_path, "judge")
    put_units(st, s, [{"id": f"u{n}"} for n in range(5)])
    calls = []

    def process(unit, store, spec):
        calls.append(unit["id"])
        if unit["id"] == "u3" and calls.count("u3") == 1:
            raise RuntimeError("worker lost")
        return f"out {unit['id']}".encode(), "txt", {"model": "m"}

    first = runner.run(s, st, process, executor="local", log=lambda m: None)
    assert first["done"] == 4 and first["failed"] == 1
    assert runner.finish(s, st)["complete"] is False
    second = runner.run(s, st, process, executor="local", log=lambda m: None)
    assert second == {**second, "done": 1, "skipped": 4, "failed": 0}
    assert calls.count("u0") == 1 and calls.count("u3") == 2
    manifest = runner.finish(s, st)
    assert manifest["complete"] and set(manifest["units"]) == {f"u{n}" for n in range(5)}
    assert runner.verify(s, st) == []


def test_workers_split_units_and_verify_catches_a_changed_output(tmp_path):
    st = store_mod.LocalStore(tmp_path)
    s = write_spec(tmp_path, "judge")
    put_units(st, s, [{"id": f"u{n}"} for n in range(6)])
    seen = {0: [], 1: []}
    for w in (0, 1):
        runner.run(s, st, lambda u, store, spec, w=w: (seen[w].append(u["id"]) or b"x", "txt", {}),
                   executor="k8s", worker=w, workers=2, log=lambda m: None)
    assert seen[0] == ["u0", "u2", "u4"] and seen[1] == ["u1", "u3", "u5"]
    runner.finish(s, st)
    prefix = s.run_prefix(runner.read_units(st, s)[1])
    key = json.loads(st.get(f"{prefix}/manifest.json"))["units"]["u2"]["key"]
    (tmp_path / key).write_bytes(b"tampered")
    assert any("does not match" in p for p in runner.verify(s, st))


def test_a_done_marker_without_its_output_reruns_the_unit(tmp_path):
    st = store_mod.LocalStore(tmp_path)
    s = write_spec(tmp_path, "judge")
    put_units(st, s, [{"id": "u0"}])
    runner.run(s, st, lambda u, store, spec: (b"x", "txt", {}), executor="local", log=lambda m: None)
    prefix = s.run_prefix(runner.read_units(st, s)[1])
    (tmp_path / prefix / "units" / "u0.txt").unlink()
    assert runner.unit_done(st, prefix, "u0") is None


def test_embed_writes_unit_vectors_in_input_order(tmp_path):
    st = store_mod.LocalStore(tmp_path)
    s = write_spec(tmp_path, "embed", "batch = 2")
    rows = [{"passage_id": f"p{n}", "text": f"text {n}"} for n in range(5)]
    st.put(f"{s.input_prefix}/shards/s0.jsonl.gz", embed.write_shard(rows))
    put_units(st, s, [{"id": "s0"}])
    fake = lambda texts: np.array([[float(len(t)), 1.0] + [0.0] * 382 for t in texts], dtype=np.float32)
    proc = embed.make_process(s, "local", embed_fn=fake, backend_name="fake")
    runner.run(s, st, proc, executor="local", log=lambda m: None)
    out = np.load(io.BytesIO(st.get(runner.finish(s, st)["units"]["s0"]["key"])))
    assert list(out["ids"]) == [f"p{n}" for n in range(5)]
    assert out["matrix"].shape == (5, 384)
    assert np.allclose(np.linalg.norm(out["matrix"], axis=1), 1.0)


def test_embed_refuses_the_wrong_dimension(tmp_path):
    st = store_mod.LocalStore(tmp_path)
    s = write_spec(tmp_path, "embed")
    st.put(f"{s.input_prefix}/shards/s0.jsonl.gz", embed.write_shard([{"passage_id": "p", "text": "t"}]))
    proc = embed.make_process(s, "local", embed_fn=lambda texts: np.zeros((len(texts), 10), dtype=np.float32),
                              backend_name="fake")
    with pytest.raises(ValueError, match="shape"):
        proc({"id": "s0"}, st, s)


def sentence_item():
    return {"item_id": "c:q1:s1", "kind": "sentence", "collection": "c", "qid": "q1", "question": "What clinics opened?",
            "filters": {}, "sentence_no": 1, "sentence": "The ministry opened 12 clinics in 1974.",
            "answer_text": "The ministry opened 12 clinics in 1974.",
            "citations": [{"passage_id": "i#1:0", "item_id": "i", "leaf_index": 1, "text": "Twelve clinics opened in 1974.",
                           "deep_link": "https://archive.org/details/i/page/n1", "title": "t", "year": 1974,
                           "jurisdiction": "ontario"}], "retrieved_ids": ["i#1:0"]}


def test_judge_records_verdicts_and_never_turns_an_unreadable_reply_into_a_pass(tmp_path):
    st = store_mod.LocalStore(tmp_path)
    s = write_spec(tmp_path, "judge")
    st.put(f"{s.input_prefix}/items/u0.jsonl", (json.dumps(sentence_item()) + "\n").encode())
    put_units(st, s, [{"id": "u0"}])
    replies = iter([{"choices": [{"message": {"content": "not json"}, "finish_reason": "stop"}]}])
    proc = judge.make_process(s, "local", post=lambda url, headers, body: next(replies))
    runner.run(s, st, proc, executor="local", log=lambda m: None)
    rec = json.loads(st.get(runner.finish(s, st)["units"]["u0"]["key"]).decode().splitlines()[0])
    assert rec["verdicts"] is None and rec["error"].startswith("unreadable")


def test_paid_judge_needs_a_cap(tmp_path, monkeypatch):
    s = write_spec(tmp_path, "judge", "")
    path = s.path
    path.write_text(path.read_text(encoding="utf-8") + '\n[executor.workers_ai]\nmodel = "@cf/openai/gpt-oss-120b"\n', encoding="utf-8")
    s = spec_mod.load(str(path))
    monkeypatch.setenv("CF_ACCOUNT_ID", "acct")
    monkeypatch.setenv("CF_AI_TOKEN", "tok")
    with pytest.raises(RuntimeError, match="run_cap_usd"):
        judge.make_process(s, "workers_ai", post=lambda *a: {})


def test_ocr_keeps_the_old_text_and_scores_both(tmp_path):
    st = store_mod.LocalStore(tmp_path)
    s = write_spec(tmp_path, "ocr", 'engine = "tesseract"')
    page = {"page_ref": "i#3", "item_id": "i", "leaf": 3, "old_text": "Tbe rnimstry opened clinics", "old_quality": 0.2}
    st.put(f"{s.input_prefix}/pages/u0.jsonl", (json.dumps(page) + "\n").encode())
    put_units(st, s, [{"id": "u0"}])
    fetched = []
    proc = ocr.make_process(s, "local", engine_fn=lambda img: ("The ministry opened clinics", "fake 1"),
                            get=lambda url: fetched.append(url) or b"jpeg", lexicon={"the", "ministry", "opened", "clinics"})
    runner.run(s, st, proc, executor="local", log=lambda m: None)
    rec = json.loads(st.get(runner.finish(s, st)["units"]["u0"]["key"]).decode().splitlines()[0])
    assert rec["old_text"] == page["old_text"] and rec["new_text"] == "The ministry opened clinics"
    assert rec["proxy"] == {"old": 0.5, "new": 1.0}
    assert fetched == ["https://archive.org/download/i/page/n3.jpg"]
    # The scan is cached in the store: a second read does not fetch it again.
    ocr.page_image(st, s, "i", 3, get=lambda url: (_ for _ in ()).throw(AssertionError("fetched twice")))


def test_lexicon_rate_is_none_without_words():
    assert ocr.lexicon_rate("12 34 ..", {"x"}) is None


def test_compile_numbers_pages_by_the_viewers_leaves_and_never_guesses(tmp_path):
    import gzip as gz
    from archive_debugger.jobs import compile as comp
    text = "COLOUR CARD|Title page of the report|Page seventy five text about hospital beds"
    index = [[0, 11, 0, 0], [12, 36, 0, 0], [37, len(text), 0, 0]]
    numbers = {"pages": [{"leafNum": 1, "pageNumber": ""}, {"leafNum": 2, "pageNumber": "75"}]}
    files = {"searchtext": gz.compress(text.encode()), "pageindex": gz.compress(json.dumps(index).encode()),
             "page_numbers": gz.compress(json.dumps(numbers).encode())}
    lines = comp.compile_item("itemx", files, {"title": "t"}, target_tokens=300, overlap_tokens=40)
    pages = [l for l in lines if l["kind"] == "page"]
    assert [(p["page_id"], p["printed_page"]) for p in pages] == [("itemx#0", None), ("itemx#1", "75")]
    passages = [l for l in lines if l["kind"] == "passage"]
    assert passages[0]["passage_id"] == "itemx#0:0" and passages[1]["text"].startswith("Page seventy five")
    # Without page_numbers the item gets no pages at all, and says why.
    del files["page_numbers"]
    lines = comp.compile_item("itemx", files, {}, target_tokens=300, overlap_tokens=40)
    assert [l["kind"] for l in lines] == ["item", "skipped"]
