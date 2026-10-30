"""Write config/cache_key_vectors.json: inputs with their expected answer-cache keys, cleaned
question and salient terms, which the Python engine (tests/test_cache.py) and the TypeScript
engine Worker (worker/engine tests) must both reproduce exactly. Rerun after any change to the key
algorithm in src/archive_debugger/api/cache.py, and commit the file with that change.

    python scripts/v2/make_cache_vectors.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from archive_debugger.api.app import clean_question
from archive_debugger.api.cache import KEY_VERSION, canonical_filters, content_key, normalize_question
from archive_debugger.generate.answer import salient_terms

OUT = Path("config/cache_key_vectors.json")
CONTEXT = "df10d4aacd93d46e63899e4b693eb278671e186c8c4bf2274e6d5d1c95db8f59"

CASES = [
    ("plain", "How did tobacco control policy change in Ontario?", {}),
    ("filters", "What did Alberta reports say about mental health services?", {"jurisdiction": "alberta"}),
    ("filter order and blanks", "q", {"period": " 1980s ", "jurisdiction": "ontario", "doc_type": ""}),
    ("min_ocr number", "q", {"min_ocr": 0.5}),
    ("min_ocr integer", "q", {"min_ocr": 1}),
    ("min_ocr zero dropped", "q", {"min_ocr": 0}),
    ("min_ocr string", "q", {"min_ocr": "0.25"}),
    ("unknown filter ignored", "q", {"colour": "red"}),
    ("none filters", "q", None),
    ("spaces collapse", "  vaccination   hospital  ", {}),
    ("tabs and newlines become spaces", "vaccination\thospital\nfunding\r\n", {}),
    ("control characters", "vaccination\x00\x07\x1fhospital\x7f", {}),
    ("case kept", "Vaccination Hospital", {}),
    ("NFD becomes NFC", "Que\u0301bec sante\u0301 publique", {}),
    ("NFC unchanged", "Qu\u00e9bec sant\u00e9 publique", {}),
    ("non-breaking space kept", "public\u00a0health", {}),
    ("emoji", "\U0001f600 public health", {}),
    ("lone surrogate replaced", "public \ud800 health", {}),
    ("quotes and backslash", 'say "hello" \\ goodbye', {}),
    ("empty", "", {}),
    ("only control and spaces", " \x01 \t ", {}),
    ("long", "public health policy funding hospital " * 30, {}),
    ("terms with years and decades", "What changed in Ontario tobacco policy between 1985 and the 1990s?", {}),
    ("terms with stopwords and repeats", "What did the reports say, and what did the reports not say?", {}),
    ("terms with accents and digits", "Sant\u00e9 publique au Qu\u00e9bec 1972 3 vaccins", {}),
    ("terms with underscore and hyphen", "co-operative health_care plans", {}),
]


def build() -> dict:
    vectors = []
    for name, question, filters in CASES:
        vectors.append({
            "name": name,
            "question": question,
            "filters": filters,
            "normalized_question": normalize_question(question),
            "canonical_filters": canonical_filters(filters),
            "key": content_key(CONTEXT, question, filters),
            "clean_question": clean_question(question),
            "salient_terms": salient_terms(clean_question(question)),
        })
    return {"key_version": KEY_VERSION, "context": CONTEXT, "vectors": vectors}


def main() -> int:
    text = json.dumps(build(), indent=1, ensure_ascii=True) + "\n"
    OUT.write_text(text, encoding="ascii")
    print(f"wrote {OUT} ({len(CASES)} vectors)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
