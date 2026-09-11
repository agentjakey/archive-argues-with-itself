"""The frozen English stoplist shared by the abstention gate (generate.answer) and,
when [retrieve].fts_drop_stopwords is on, the FTS query builder. Moved here from
generate/answer.py in Phase 13 so retrieve/ never imports generate/; the content is
unchanged and frozen (see reports/phase9/generation_report.md, Amendment)."""
from __future__ import annotations

# Fixed English stopwords: articles, conjunctions, prepositions, pronouns,
# auxiliaries, question words. Deliberately no domain words.
_STOP_FUNCTION = frozenset({
    "a", "an", "the",
    "and", "or", "but", "if", "so", "than", "as", "not", "no",
    "of", "to", "in", "on", "at", "by", "for", "from", "with", "about", "into",
    "over", "under", "between", "through", "during", "before", "after",
    "i", "me", "my", "we", "our", "you", "your", "he", "him", "his", "she", "her",
    "it", "its", "they", "them", "their", "this", "that", "these", "those",
    "is", "are", "was", "were", "be", "been", "being", "do", "does", "did",
    "have", "has", "had", "will", "would", "shall", "should", "can", "could",
    "may", "might", "must",
    "what", "which", "who", "whom", "whose", "when", "where", "why", "how",
})
# Amendment, made once after sweep 1. Criterion (a): verbs and nouns that describe
# the act of asking or the form of the answer, not the subject matter.
_STOP_ASKING = frozenset({
    "describe", "explain", "discuss", "compare", "conclude", "conclusion", "conclusions",
    "recommend", "recommendation", "recommendations", "report", "reported", "state",
    "stated", "say", "said", "address", "addressed", "identify", "shift", "shifted",
    "change", "changed", "evolve", "evolved", "differ", "differed",
})
# Criterion (b): generic actor nouns that name who acted, not what was done.
_STOP_ACTORS = frozenset({
    "authorities", "authority", "officials", "government", "governments",
    "department", "departments", "ministry", "agency", "agencies",
})
STOPWORDS = _STOP_FUNCTION | _STOP_ASKING | _STOP_ACTORS
