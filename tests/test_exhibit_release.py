"""The exhibit in a release: the gate that reads the published deck (a seeded bad round is refused
from the published text alone), and the kiosk server (its headers, its daily totals, install and
rollback). No test reaches a real host."""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import socket
from pathlib import Path

import pytest

from archive_debugger.exhibit import release, settings

REPO = Path(__file__).resolve().parent.parent


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("a test tried to open a network connection")
    monkeypatch.setattr(socket, "create_connection", refuse)


def serve_module():
    spec = importlib.util.spec_from_file_location("exhibit_serve", REPO / "exhibit" / "kiosk" / "serve.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


PAGE_TEXT = "Most claims came from the construction and logging industries.\nA new safety program began."


def good_round() -> dict:
    page = {
        "ref": "wcb1978#12", "collection": "c", "item_id": "wcb1978", "leaf": 12, "title": "Annual report",
        "issuer": "wcb", "jurisdiction": "new_brunswick", "language": "eng",
        "catalogue_date": {"year": 1978, "raw": "1978-01-01", "method": "exact"},
        "page_date": {"year": 1978, "method": "read_from_front_matter", "page_ref": "wcb1978#1", "line": "ANNUAL REPORT 1978"},
        "date_verified": True, "date_verification": "catalogue_and_page_agree", "text": PAGE_TEXT, "text_cut": False,
        "text_sha256": "x" * 64, "passage_ids": ["wcb1978#12:0"],
        "details_url": "https://archive.org/details/wcb1978/page/n12",
        "image_url": "https://archive.org/download/wcb1978/page/n12_medium.jpg",
        "thumb_url": "https://archive.org/download/wcb1978/page/n12_thumb.jpg",
    }
    return {
        "id": "wwt-1", "mode": "when_was_this", "level": 1, "collection": "c", "pages": [page],
        "quotes": [{"id": "c1", "page_ref": "wcb1978#12", "role": "clue", "text": "A new safety program began."}],
        "play": {"year": 1978, "label": {"en": "A report", "fr": "Un rapport"}, "clues": ["c1"], "masked_text": [], "masked_title": []},
        "explanation": {"en": "A new program.", "fr": "Un nouveau programme."}, "explanation_status": "model-drafted",
        "care_flags": [], "status": "model-reviewed",
        "checks": {"builder_version": "1", "refusals": [], "checked_at": "x", "fingerprint": "f"},
        "review": {}, "provenance": {"drafted_by": "m", "prompt_version": "p", "drafted_at": "x", "edits": []},
    }


def make_release(tmp_path: Path, rounds: list, extra_files: dict | None = None) -> Path:
    rel = tmp_path / "release"
    (rel / "exhibit" / "decks").mkdir(parents=True)
    (rel / "exhibit" / "index.html").write_text("<!doctype html>", encoding="utf-8")
    deck = {"format": "exhibit-deck/1", "deck_id": "t", "built_at": "x", "builder_version": "1",
            "settings": {"panel_calibrated": False}, "counts": {}, "rounds": rounds, "gap_hunt": None}
    raw = json.dumps(deck).encode("utf-8")
    name = release.deck_file_name(deck, raw)
    (rel / "exhibit" / "decks" / name).write_bytes(raw)
    (rel / "exhibit" / release.POINTER).write_text(json.dumps({"deck": name, "deck_id": "t",
                                                                "sha256": hashlib.sha256(raw).hexdigest()}), encoding="utf-8")
    for path, content in (extra_files or {}).items():
        (rel / path).parent.mkdir(parents=True, exist_ok=True)
        (rel / path).write_bytes(content)
    return rel


def test_a_good_exhibit_passes(tmp_path):
    assert release.exhibit_problems(make_release(tmp_path, [good_round()]), settings.load()) == []


def test_no_exhibit_is_no_problem(tmp_path):
    assert release.exhibit_problems(tmp_path, settings.load()) == []


@pytest.mark.parametrize("mutate, expected", [
    (lambda r: r["quotes"][0].update(text="A new mining program began."), "is not in the page text the round shows"),
    (lambda r: r["pages"][0].update(date_verified=False), "date is not verified"),
    (lambda r: r["play"].update(year=1980), "scored year is not the page's verified year"),
    (lambda r: r["pages"][0].update(image_url="https://example.com/copy.jpg"), "image_url is not that page"),
    (lambda r: r["pages"][0].update(details_url="https://archive.org/details/other/page/n12"), "no link to its own page"),
    (lambda r: r.update(status="flagged"), "is not publishable"),
    (lambda r: r["checks"].update(refusals=["quote_not_on_page:c1"]), "the builder did not pass"),
    (lambda r: r["explanation"].update(en="It mentions a residential school."), "excluded care topics"),
])
def test_seeded_bad_rounds_are_refused_from_the_published_text(tmp_path, mutate, expected):
    bad = copy.deepcopy(good_round())
    mutate(bad)
    problems = release.exhibit_problems(make_release(tmp_path, [bad]), settings.load())
    assert any(expected in p for p in problems), problems


def test_a_pointer_that_does_not_match_its_deck_is_refused(tmp_path):
    rel = make_release(tmp_path, [good_round()])
    pointer = json.loads((rel / "exhibit" / release.POINTER).read_text(encoding="utf-8"))
    pointer["sha256"] = "0" * 64
    (rel / "exhibit" / release.POINTER).write_text(json.dumps(pointer), encoding="utf-8")
    assert any("sha256" in p for p in release.exhibit_problems(rel, settings.load()))


def test_page_images_are_refused_while_offline_caching_is_off(tmp_path):
    rel = make_release(tmp_path, [good_round()], {"exhibit/pages/wcb1978/n12_medium.jpg": b"\xff\xd8"})
    assert any("offline caching is off" in p for p in release.exhibit_problems(rel, settings.load()))


def test_kiosk_headers_follow_the_release(tmp_path):
    serve = serve_module()
    rules = serve.parse_headers("/*\n  Content-Security-Policy: default-src 'self'\n\n/exhibit/assets/*\n  Cache-Control: immutable\n")
    names = [n for n, _ in serve.headers_for(rules, "/exhibit/assets/x.js")]
    assert names == ["Content-Security-Policy", "Cache-Control"]
    assert [n for n, _ in serve.headers_for(rules, "/exhibit/")] == ["Content-Security-Policy"]


def test_kiosk_counts_are_daily_totals_of_event_words_only(tmp_path):
    serve = serve_module()
    counts = serve.DailyCounts(tmp_path / "counts")
    assert counts.add("same_or_not:start")
    assert counts.add("same_or_not:start")
    assert not counts.add("visitor@example.com")
    assert not counts.add("same_or_not:start 12:31")
    counts.flush()
    files = list((tmp_path / "counts").glob("*.json"))
    assert len(files) == 1
    assert json.loads(files[0].read_text(encoding="utf-8")) == {"same_or_not:start": 2}


def test_kiosk_install_and_rollback(tmp_path):
    serve = serve_module()
    root = tmp_path / "kiosk"
    for rid in ("r1", "r2"):
        rel = tmp_path / rid
        (rel / "exhibit").mkdir(parents=True)
        (rel / "exhibit" / "index.html").write_text(rid, encoding="utf-8")
        (rel / "release-manifest.json").write_text(json.dumps({"release_id": rid}), encoding="utf-8")
        serve.install(root, rel)
    assert serve.current_release(root).name == "r2"
    assert serve.rollback(root) == "r1"
    assert serve.current_release(root).name == "r1"
    with pytest.raises(SystemExit):
        serve.rollback(root)
