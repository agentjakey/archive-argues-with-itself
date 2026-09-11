"""Hybrid retrieval: BM25 (FTS5) + dense (sqlite-vec flat, exact) fused with RRF,
OCR soft down-weight, page-level provenance attached. Read-only over civic.db and
the vectors.db artifact.

Phase 13 switches, all read from RetrieveConfig and off by default:
- fts_drop_stopwords: drop the frozen stoplist before building the OR query.
- section_demote: multiply the fused score by a per-class weight for pages the
  ingest classifier marked front or back matter (never excludes).
- doc_type_family_filter: a doc_type filter matches its whole configured family.
- per_item_cap: at most N passages per item in the ranking (0 = off).
- later_years_flag: annotate a hit with years in its text later than item year + 1."""
from __future__ import annotations

import re
import sqlite3
from collections import Counter
from pathlib import Path
from typing import Optional

import sqlite_vec

from archive_debugger.retrieve import citation
from archive_debugger.retrieve.config import RetrieveConfig, load_retrieve_config
from archive_debugger.retrieve.embed import Embedder, make_embedder
from archive_debugger.retrieve.filters import Filters, build_where
from archive_debugger.retrieve.fusion import apply_downweight, apply_section_weight, rrf
from archive_debugger.stopwords import STOPWORDS

_WORD = re.compile(r"[^\W_]+", re.UNICODE)
_YEAR = re.compile(r"\b(1[89]\d\d|20\d\d)\b")


class Retriever:
    def __init__(self, config_path: Optional[Path], *, embedder: Optional[Embedder] = None,
                 cfg: Optional[RetrieveConfig] = None):
        self.cfg = cfg or load_retrieve_config(config_path)
        # Read-only. check_same_thread=False lets a server's worker threads use the one
        # connection; callers that share a Retriever across threads must serialize access.
        self.conn = sqlite3.connect(f"file:{self.cfg.db_path}?mode=ro", uri=True, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.enable_load_extension(True)
        sqlite_vec.load(self.conn)
        self.conn.enable_load_extension(False)
        self.conn.execute("ATTACH DATABASE ? AS vec", (f"file:{self.cfg.index_path}?mode=ro",))
        self.embedder = embedder or make_embedder(self.cfg.embedder, self.cfg.embedding_model, self.cfg.embedding_dim)
        # A db built before Phase 13 has no section column; treat every page as body.
        self._has_sections = "section_class" in {r[1] for r in self.conn.execute("PRAGMA table_info(pages)")}

    def close(self) -> None:
        self.conn.close()

    def _fts_query(self, query: str) -> str:
        terms = _WORD.findall(query.lower())
        if self.cfg.fts_drop_stopwords:
            kept = [t for t in terms if t not in STOPWORDS]
            terms = kept or terms            # an all-stopword question still queries something
        if not terms:
            return '""'
        return " OR ".join('"' + t.replace('"', '""') + '"' for t in terms)

    def _bm25(self, query: str, where: str, params: list, k: int) -> list[str]:
        sql = ("SELECT p.passage_id FROM passages_fts f "
               "JOIN passages p ON p.rowid = f.rowid "
               "JOIN items i ON i.item_id = p.item_id "
               "WHERE passages_fts MATCH ?" + where +
               " ORDER BY bm25(passages_fts) LIMIT ?")
        return [r[0] for r in self.conn.execute(sql, [self._fts_query(query), *params, k])]

    def _dense(self, qvec: list[float], where: str, params: list, k: int) -> list[str]:
        sql = ("SELECT p.passage_id FROM vec.passages_vec v "
               "JOIN passages p ON p.passage_id = v.passage_id "
               "JOIN items i ON i.item_id = p.item_id "
               "WHERE 1 = 1" + where +
               " ORDER BY vec_distance_cosine(v.embedding, ?) LIMIT ?")
        return [r[0] for r in self.conn.execute(sql, [*params, sqlite_vec.serialize_float32(qvec), k])]

    def _passage_meta(self, pids: set) -> dict:
        """pid -> (ocr_quality, section_class, item_id) for the fused candidates."""
        if not pids:
            return {}
        marks = ",".join("?" * len(pids))
        section = "g.section_class" if self._has_sections else "NULL"
        rows = self.conn.execute(
            f"SELECT p.passage_id, CAST(p.ocr_quality AS REAL), {section}, p.item_id "
            f"FROM passages p LEFT JOIN pages g ON g.page_id = p.page_id WHERE p.passage_id IN ({marks})",
            list(pids),
        )
        return {pid: ((q if q is not None else 1.0), sec, item) for pid, q, sec, item in rows}

    def _rank(self, final: dict, item_of: dict) -> list[str]:
        ranked = sorted(final, key=lambda p: final[p], reverse=True)
        cap = self.cfg.per_item_cap
        if cap <= 0:
            return ranked
        out: list[str] = []
        per_item: Counter = Counter()
        for pid in ranked:
            item = item_of.get(pid)
            if per_item[item] >= cap:
                continue
            per_item[item] += 1
            out.append(pid)
        return out

    def _later_years(self, year, text: str):
        if not self.cfg.later_years_flag or year is None:
            return None
        later = sorted({int(y) for y in _YEAR.findall(text or "") if int(y) > int(year) + 1})
        return later or None

    def _provenance(self, pid: str, score: float) -> dict:
        # LEFT JOIN + fail-loud: a retrieved passage that cannot resolve to a real
        # page/item is a bug we must see, never a silent drop that shortens results
        # and corrupts the citation audit (N2).
        # leaf_index/item_id are sourced from the JOINED pages/items so a missing
        # row surfaces as NULL and trips the assertion below, rather than being
        # masked by the passage's own copies of those columns.
        r = self.conn.execute(
            "SELECT p.passage_id, i.item_id AS item_id, g.leaf_index AS leaf_index, "
            "p.char_start, p.char_end, p.text, "
            "CAST(p.ocr_quality AS REAL) AS ocr_quality, g.printed_page, i.title, i.details_url, "
            "i.year, i.decade, i.dated, i.jurisdiction_norm, i.issuer_norm, i.doc_type_norm "
            "FROM passages p LEFT JOIN pages g ON g.page_id = p.page_id "
            "LEFT JOIN items i ON i.item_id = p.item_id WHERE p.passage_id = ?",
            (pid,),
        ).fetchone()
        if r is None or r["leaf_index"] is None or r["item_id"] is None:
            raise LookupError(f"passage {pid} has no resolvable page/item provenance")
        leaf = r["leaf_index"]
        return {
            "passage_id": r["passage_id"],
            "score": score,
            "text": r["text"],
            "char_start": r["char_start"],
            "char_end": r["char_end"],
            "ocr_quality": r["ocr_quality"],
            "item_id": r["item_id"],
            "title": r["title"],
            "leaf_index": leaf,
            "printed_page": r["printed_page"],
            "page_deep_link": citation.deep_link(r["item_id"], leaf),
            "details_url": r["details_url"],
            "year": r["year"],
            "decade": r["decade"],
            "dated": r["dated"],
            "jurisdiction": r["jurisdiction_norm"],
            "issuer": r["issuer_norm"],
            "doc_type": r["doc_type_norm"],
            "later_years": self._later_years(r["year"], r["text"]),
        }

    def lookup(self, passage_ids: list[str]) -> list[dict]:
        """Provenance rows for known passage ids, in the given order, without ranking
        (stories and pinned comparisons). Unknown ids raise LookupError."""
        meta = self._passage_meta(set(passage_ids))
        out = []
        for pid in passage_ids:
            hit = self._provenance(pid, 0.0)
            hit["bm25_rank"] = None
            hit["dense_rank"] = None
            hit["section_class"] = (meta.get(pid, (None, None, None))[1]) or "body"
            out.append(hit)
        return out

    def search(self, query: str, filters: Optional[Filters] = None, top_k: int = 20) -> list[dict]:
        where, params = build_where(filters or Filters(), doc_type_families=self.cfg.active_families())
        bm = self._bm25(query, where, params, self.cfg.candidates)
        qvec = self.embedder.embed_query(query)
        dn = self._dense(qvec, where, params, self.cfg.candidates)
        fused = rrf([bm, dn], k=self.cfg.rrf_k)
        if not fused:
            return []
        bm_rank = {pid: i + 1 for i, pid in enumerate(bm)}
        dn_rank = {pid: i + 1 for i, pid in enumerate(dn)}
        meta = self._passage_meta(set(fused))
        final = apply_downweight(fused, {pid: m[0] for pid, m in meta.items()}, self.cfg.downweights)
        if self.cfg.section_demote:
            final = apply_section_weight(final, {pid: m[1] for pid, m in meta.items()}, self.cfg.section_weights)
        ranked = self._rank(final, {pid: m[2] for pid, m in meta.items()})[:top_k]
        out = []
        for pid in ranked:
            hit = self._provenance(pid, final[pid])
            hit["bm25_rank"] = bm_rank.get(pid)    # None if the passage came only from the dense leg
            hit["dense_rank"] = dn_rank.get(pid)   # None if it came only from BM25
            hit["section_class"] = (meta.get(pid, (None, None, None))[1]) or "body"
            out.append(hit)
        return out
