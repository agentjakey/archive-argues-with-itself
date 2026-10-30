"""Curated stories and editorial notes: the data rules both the API and the static build follow.

A story is a question plus two pinned pages and an author's caption. Every story carries a
comparability block naming one of the six comparison outcomes (COMPARISON_OUTCOMES below),
the query constraints the two pages differ on, and a plain note. The caption, the question and the
labels around them must not claim more than that block supports: a pair that is not comparable is
never framed as a change, a continuity, or a disagreement.

Editorial notes (config/editorial_notes.json) are dated, visible corrections. They are data, not
code: the API serves them and the web app renders them, and a static build reads the same file. A
note never edits model output; it sits beside it.
"""
from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path
from typing import Optional

DEFAULT_NOTES = Path("config/editorial_notes.json")
DEFAULT_RETIRED = Path("config/retired_stories.json")

COMPARISON_OUTCOMES = {
    "comparable_agreeing": "Comparable and agreeing",
    "comparable_disagreeing": "Comparable and disagreeing",
    "related_different": "Related but describing different things",
    "incompatible": "Incompatible",
    "missing": "Missing",
    "indeterminate": "Indeterminate",
}
COMPARABLE = {"comparable_agreeing", "comparable_disagreeing"}
DIFFERS_ON = {"subject", "period", "jurisdiction", "population", "program", "measure"}
SURFACES = {"hero", "gallery", "attract"}
NOTE_KINDS = {"story", "answer"}

# Wording that frames two pages as one thing changing, continuing, or disagreeing. Allowed only on a
# pair marked comparable (and disagreement language only on a comparable_disagreeing pair).
_CONTINUITY = [
    re.compile(r"\bthe same (insurance )?(plan|program|programme|policy|registry|scheme)\b", re.I),
    re.compile(r"\bthen (a|an|the)\b", re.I),
    re.compile(r",\s*then\b", re.I),
    re.compile(r"\b(shift|shifted|shifts|evolved|evolution|replaced|became|went from|led to)\b", re.I),
    re.compile(r"\bwhat changed\b", re.I),
]
_DISAGREEMENT = [
    re.compile(r"\b(disagree|disagrees|disagreed|disagreement|contradict\w*|conflict\w*)\b", re.I),
    re.compile(r"\bargues? with\b", re.I),
]
_CHANGE_WORD = re.compile(r"\bchang(e|ed|es|ing)\b", re.I)
_NEGATION = re.compile(r"\b(not|cannot|can't|never|no|neither|nor)\b", re.I)
_CHANGE_QUESTION = re.compile(r"\bhow (did|has|have|do|does)\b.*\bchang", re.I)


class StoryError(ValueError):
    pass


def _sentences(text: str) -> list[str]:
    return [s for s in re.split(r"(?<=[.!?])\s+", text or "") if s.strip()]


def overclaims(text: str, outcome: str) -> list[str]:
    """The phrases in text that assert more than a pair with this comparison outcome supports. Change
    and continuity wording is allowed only in a sentence that negates it ("cannot show how coverage
    changed", "neither page shows what led to it")."""
    found: list[str] = []
    if outcome not in COMPARABLE:
        for sentence in _sentences(text):
            if _NEGATION.search(sentence):
                continue
            for pat in _CONTINUITY:
                found += [m.group(0) for m in pat.finditer(sentence)]
            if _CHANGE_WORD.search(sentence):
                found.append(_CHANGE_WORD.search(sentence).group(0))
    if outcome != "comparable_disagreeing":
        for pat in _DISAGREEMENT:
            found += [m.group(0) for m in pat.finditer(text or "")]
    return found


def question_presupposes_change(question: str) -> bool:
    return bool(_CHANGE_QUESTION.search(question or ""))


def validate_story(s: dict, *, require_surfaces: bool = True) -> None:
    """Structural checks every story must pass to load. Raises StoryError naming the story."""
    sid = s.get("id")
    if not (sid and s.get("question") and isinstance(s.get("pins"), list) and len(s["pins"]) == 2):
        raise StoryError(f"story {sid!r} needs id, question, and exactly two pins")
    comp = s.get("comparability")
    if not isinstance(comp, dict):
        raise StoryError(f"story {sid!r} has no comparability block")
    if comp.get("outcome") not in COMPARISON_OUTCOMES:
        raise StoryError(f"story {sid!r}: comparability.outcome must be one of {sorted(COMPARISON_OUTCOMES)}")
    differs = comp.get("differs_on")
    if not isinstance(differs, list) or not set(differs) <= DIFFERS_ON:
        raise StoryError(f"story {sid!r}: comparability.differs_on must be a list drawn from {sorted(DIFFERS_ON)}")
    if comp["outcome"] not in COMPARABLE and not differs:
        raise StoryError(f"story {sid!r}: a pair that is not comparable must name what it differs on")
    if not (comp.get("note") or "").strip():
        raise StoryError(f"story {sid!r}: comparability.note is empty")
    if require_surfaces:
        surfaces = s.get("surfaces")
        if not isinstance(surfaces, list) or not surfaces or not set(surfaces) <= SURFACES:
            raise StoryError(f"story {sid!r}: surfaces must be a non-empty list drawn from {sorted(SURFACES)}")
    if "answer_question" in s and not (s["answer_question"] or "").strip():
        raise StoryError(f"story {sid!r}: answer_question, when present, must not be empty")


def asked_question(story: dict) -> str:
    """The question a story's answer is asked (and cached) with. Usually the shown question; a
    corrected story keeps its original wording here so its stored answer still serves, unedited,
    beside a dated note."""
    return story.get("answer_question") or story["question"]


def load_stories(path: Path) -> list[dict]:
    if not Path(path).exists():
        return []
    stories = json.loads(Path(path).read_text(encoding="utf-8"))
    seen = set()
    for s in stories:
        validate_story(s)
        if s["id"] in seen:
            raise StoryError(f"story id {s['id']!r} appears twice")
        seen.add(s["id"])
    if sum(1 for s in stories if "hero" in s["surfaces"]) > 1:
        raise StoryError(f"{path}: at most one story may carry the hero surface")
    return stories


def load_retired(path: Path = DEFAULT_RETIRED) -> list[dict]:
    if not Path(path).exists():
        return []
    retired = json.loads(Path(path).read_text(encoding="utf-8"))
    for s in retired:
        validate_story(s, require_surfaces=False)
        if not (s.get("scope") and s.get("retired")):
            raise StoryError(f"retired story {s.get('id')!r} needs scope and retired date")
        date.fromisoformat(s["retired"])
    return retired


def load_notes(path: Path = DEFAULT_NOTES) -> dict:
    """The versioned editorial-notes file. Missing file means no notes. Malformed raises."""
    if not Path(path).exists():
        return {"version": 0, "notes": []}
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data.get("version"), int) or not isinstance(data.get("notes"), list):
        raise StoryError(f"{path}: needs an integer version and a notes list")
    ids = set()
    for n in data["notes"]:
        nid = n.get("id")
        if not nid or nid in ids:
            raise StoryError(f"{path}: note id {nid!r} missing or duplicated")
        ids.add(nid)
        target = n.get("target") or {}
        if target.get("kind") not in NOTE_KINDS or not target.get("scope"):
            raise StoryError(f"note {nid!r}: target needs kind in {sorted(NOTE_KINDS)} and a scope")
        if target["kind"] == "story" and not target.get("story_id"):
            raise StoryError(f"note {nid!r}: a story target needs story_id")
        if target["kind"] == "answer" and not target.get("question"):
            raise StoryError(f"note {nid!r}: an answer target needs the question it was asked with")
        date.fromisoformat(n.get("date") or "")
        if not (n.get("text") or "").strip() or not (n.get("reason") or "").strip():
            raise StoryError(f"note {nid!r}: text and reason are required")
    return data


def _public(note: dict) -> dict:
    return {"id": note["id"], "date": note["date"], "text": note["text"], "reason": note["reason"]}


def notes_for_story(notes: dict, scope: str, story_id: str) -> list[dict]:
    out = [_public(n) for n in notes["notes"]
           if n["target"]["kind"] == "story" and n["target"]["scope"] == scope
           and n["target"]["story_id"] == story_id]
    return sorted(out, key=lambda n: (n["date"], n["id"]))


def notes_for_answer(notes: dict, scope: str, question: str, *, cached: bool) -> list[dict]:
    """Notes about an answer asked with exactly this question in this scope. A cached_only note
    describes one stored answer, so it is never attached to a freshly generated one."""
    out = []
    for n in notes["notes"]:
        t = n["target"]
        if t["kind"] != "answer" or t["scope"] != scope or t["question"] != question:
            continue
        if t.get("cached_only") and not cached:
            continue
        out.append(_public(n))
    return sorted(out, key=lambda n: (n["date"], n["id"]))


def comparability_view(story: dict) -> dict:
    comp = story["comparability"]
    return {"outcome": comp["outcome"], "label": COMPARISON_OUTCOMES[comp["outcome"]],
            "differs_on": list(comp["differs_on"]), "note": comp["note"]}


def find_story_problems(stories: list[dict], notes: dict, scope: str) -> list[str]:
    """Every way a story set claims more than its comparability blocks support, as readable lines.
    Empty means the set passes. Used by the tests and by any release gate."""
    problems = []
    for s in stories:
        outcome = s["comparability"]["outcome"]
        for field in ("caption", "question"):
            for phrase in overclaims(s.get(field, ""), outcome):
                problems.append(f"{scope}/{s['id']}: {field} says {phrase!r} but the pair is {outcome}")
        for phrase in overclaims(s["comparability"]["note"], outcome):
            problems.append(f"{scope}/{s['id']}: comparability note says {phrase!r} but the pair is {outcome}")
        if outcome not in COMPARABLE and question_presupposes_change(s["question"]):
            problems.append(f"{scope}/{s['id']}: question presupposes a change but the pair is {outcome}")
        asked = s.get("answer_question")
        if asked and asked != s["question"]:
            if not notes_for_answer(notes, scope, asked, cached=True):
                problems.append(f"{scope}/{s['id']}: answers a different question with no editorial note on that answer")
            if not notes_for_story(notes, scope, s["id"]):
                problems.append(f"{scope}/{s['id']}: question was replaced with no dated note on the story")
    return problems
