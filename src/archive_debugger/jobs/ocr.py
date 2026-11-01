"""The OCR job: read the worst pages again with a better engine, keeping the old text.

Input unit: <input_prefix>/pages/<id>.jsonl, one page per line: {"page_ref", "item_id", "leaf",
"old_text", "old_quality"} (prepared from the pages with the lowest OCR confidence). The job fetches
each page's scan from archive.org's image service, politely (one at a time, identified, cached in
the store under <input_prefix>/images/), runs the engine named in the spec, and writes <id>.jsonl:
{"page_ref", "old_text", "new_text", "engine", "engine_version", "seconds", "proxy"}. Nothing
replaces the old text: a later build chooses between them by a measured rule, and both stay.

Engines (all openly licensed): "tesseract" (Apache-2.0, the CLI), "doctr" (Apache-2.0, docTR's
pretrained detection and recognition models) and "paddleocr" (Apache-2.0). Which is best on this
collection is measured, not assumed: `proxy` is the share of words a lexicon of the collection's
clean pages knows (docs/CLUSTER.md, "Choosing the OCR engine")."""
from __future__ import annotations

import io
import json
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Callable

from archive_debugger.jobs import net
from archive_debugger.jobs.spec import JobSpec

IMAGE_URL = "https://archive.org/download/{item}/page/n{leaf}{suffix}.jpg"
WORD = re.compile(r"[^\W\d_]{3,}", re.UNICODE)


def lexicon_rate(text: str, lexicon: set) -> float | None:
    """Share of the text's words of three letters or more that the lexicon knows; None when the
    text has no such word. A proxy for OCR quality, not a measured error rate."""
    words = [w.lower() for w in WORD.findall(text or "")]
    if not words:
        return None
    return round(sum(1 for w in words if w in lexicon) / len(words), 4)


def build_lexicon(texts: list, min_count: int = 3) -> set:
    counts: dict = {}
    for t in texts:
        for w in WORD.findall(t or ""):
            w = w.lower()
            counts[w] = counts.get(w, 0) + 1
    return {w for w, n in counts.items() if n >= min_count}


def tesseract(image: bytes, lang: str = "eng+fra") -> tuple:
    exe = shutil.which("tesseract")
    if not exe:
        raise RuntimeError("tesseract is not installed (the jobs image has it)")
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "page.jpg"
        src.write_bytes(image)
        out = subprocess.run([exe, str(src), "stdout", "-l", lang, "--psm", "3"], capture_output=True, timeout=300)
        if out.returncode != 0:
            raise RuntimeError(out.stderr.decode("utf-8", "replace")[:300])
        version = subprocess.run([exe, "--version"], capture_output=True).stdout.decode().splitlines()[0]
        return out.stdout.decode("utf-8", "replace"), version


_DOCTR = {}


def doctr(image: bytes) -> tuple:
    if "model" not in _DOCTR:
        from doctr.models import ocr_predictor
        import doctr
        _DOCTR["model"] = ocr_predictor(pretrained=True)
        _DOCTR["version"] = f"doctr {doctr.__version__}"
    from doctr.io import DocumentFile
    doc = DocumentFile.from_images([image])
    result = _DOCTR["model"](doc)
    lines = []
    for page in result.pages:
        for block in page.blocks:
            for line in block.lines:
                lines.append(" ".join(w.value for w in line.words))
    return "\n".join(lines), _DOCTR["version"]


_PADDLE = {}


def paddleocr(image: bytes) -> tuple:
    if "model" not in _PADDLE:
        from paddleocr import PaddleOCR
        import paddleocr as pkg
        _PADDLE["model"] = PaddleOCR(use_angle_cls=True, lang="en", show_log=False)
        _PADDLE["version"] = f"paddleocr {pkg.__version__}"
    import numpy as np
    from PIL import Image
    arr = np.array(Image.open(io.BytesIO(image)).convert("RGB"))
    result = _PADDLE["model"].ocr(arr, cls=True)
    lines = [entry[1][0] for page in (result or []) for entry in (page or [])]
    return "\n".join(lines), _PADDLE["version"]


ENGINES = {"tesseract": tesseract, "doctr": doctr, "paddleocr": paddleocr}


def page_image(store, spec: JobSpec, item: str, leaf: int, get: Callable = None) -> bytes:
    """The page scan, from the store's cache or archive.org (then cached), at the spec's size."""
    suffix = spec.params.get("image_suffix", "")          # "" is the full scan; "_w1600" a smaller one
    key = f"{spec.input_prefix.rstrip('/')}/images/{item}/n{leaf}{suffix}.jpg"
    if store.head(key) is not None:
        return store.get(key)
    data = (get or net.get_bytes)(IMAGE_URL.format(item=item, leaf=leaf, suffix=suffix))
    store.put(key, data)
    return data


def make_process(spec: JobSpec, executor: str, *, engine_fn: Callable = None, get: Callable = None,
                 lexicon: set | None = None) -> Callable:
    name = spec.params.get("engine", "tesseract")
    engine_fn = engine_fn or ENGINES[name]

    def process(unit: dict, store, _spec: JobSpec) -> tuple:
        lex = lexicon
        if lex is None and spec.params.get("lexicon_key"):
            lex = set(store.get(spec.params["lexicon_key"]).decode("utf-8").split())
        raw = store.get(f"{spec.input_prefix.rstrip('/')}/pages/{unit['id']}.jsonl").decode("utf-8")
        rows = []
        for page in (json.loads(line) for line in raw.splitlines() if line.strip()):
            image = page_image(store, spec, page["item_id"], int(page["leaf"]), get)
            started = time.time()
            text, version = engine_fn(image)
            rows.append({"page_ref": page["page_ref"], "old_text": page["old_text"], "new_text": text,
                         "engine": name, "engine_version": version, "seconds": round(time.time() - started, 2),
                         "proxy": {"old": lexicon_rate(page["old_text"], lex) if lex else None,
                                   "new": lexicon_rate(text, lex) if lex else None}})
        body = "".join(json.dumps(r, ensure_ascii=True) + "\n" for r in rows)
        return body.encode("utf-8"), "jsonl", {"model": name, "backend": executor, "pages": len(rows)}
    return process
