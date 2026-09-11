"""Prompt assembly: each retrieved passage is tagged [passage_id] with its page-level
citation block. Key names match Retriever.search output exactly."""
from __future__ import annotations

SYSTEM = (
    "You answer civic questions using ONLY the provided passages from Canadian "
    "government public-health publications. Every sentence must list one or more "
    "passage ids in cited_ids. Never state a page number, year, or date that does not "
    "appear in a cited passage's text or in its citation block. Do not add outside "
    "knowledge. If the passages do not support a claim, do not make it."
)


def build_user_prompt(question: str, hits: list[dict]) -> str:
    parts = [f"QUESTION: {question}", "", "PASSAGES:"]
    for h in hits:
        parts.append(
            f"[{h['passage_id']}] item={h['item_id']} title={h.get('title')} year={h.get('year')} "
            f"jurisdiction={h.get('jurisdiction')} leaf={h['leaf_index']} "
            f"printed_page={h.get('printed_page')} deep_link={h['page_deep_link']}"
        )
        parts.append(h["text"])
        parts.append("")
    parts.append("Write the answer as sentences; for each sentence list the passage ids it relies on.")
    return "\n".join(parts)
