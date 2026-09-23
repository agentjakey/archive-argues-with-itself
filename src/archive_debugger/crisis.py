"""Canonical crisis-support resources and the topic-to-resource map: the SINGLE source of truth
for every crisis phone number and support line in the app. No other module or copy may hold a
crisis phone number. flags.py maps a detected topic to these resources, and the API serves them to
the frontend (per-answer via the flag, and the whole set via /scopes for static surfaces such as
the Gaps care note).

Author-final resource text; numbers verified against official sources (988.ca; Indigenous Services
Canada for Hope for Wellness, the Residential School line, and the MMIWG line). Re-verify the week
of the event. Provenance is kept in the gitignored notes/ folder, not the public repo.

Each resource carries a label, a contact instruction (call/text/chat), its hours, who it is for,
and, where it has one, a link.
"""
from __future__ import annotations

# resource_key -> resource. Everything visitor-facing is verbatim from the author's canonical set.
RESOURCES: dict[str, dict] = {
    "helpline_988": {
        "key": "helpline_988",
        "label": "9-8-8 Suicide Crisis Helpline",
        "contact": "Call or text 9-8-8",
        "hours": "24/7, free, across Canada",
        "for": "Anyone thinking about suicide or in crisis",
        "link": "988.ca",
    },
    "hope_for_wellness": {
        "key": "hope_for_wellness",
        "label": "Hope for Wellness Help Line",
        "contact": "Call 1-855-242-3310, or chat at hopeforwellness.ca",
        "hours": "24/7",
        "for": ("All First Nations, Inuit, and Metis people. Counselling in English and French, "
                "and on request Cree, Ojibway, and Inuktitut"),
        "link": "hopeforwellness.ca",
    },
    "irs_crisis_line": {
        "key": "irs_crisis_line",
        "label": "National Indian Residential School Crisis Line",
        "contact": "Call 1-866-925-4419",
        "hours": "24/7",
        "for": "Former Residential School students and their families; emotional support and crisis referral",
    },
    "mmiwg_crisis_line": {
        "key": "mmiwg_crisis_line",
        "label": "MMIWG Crisis Line",
        "contact": "Call 1-844-413-6649",
        "hours": "24/7",
        "for": "Anyone affected by Missing and Murdered Indigenous Women, Girls and 2SLGBTQQIA+ people",
    },
}

# Detection topic key (flags.TOPIC_SIGNALS keys, hyphenated) -> ordered resource keys (the list
# order is the display order). The author's spec uses underscored topic names; they map to the
# existing hyphenated detection keys one-to-one.
TOPIC_RESOURCES: dict[str, list[str]] = {
    "residential-school-health": ["irs_crisis_line", "hope_for_wellness", "helpline_988"],
    # mmiwg_crisis_line is included here deliberately (author-decided): the sterilization topic can
    # surface MMIWG-adjacent harm, so this line is offered alongside Hope for Wellness and 9-8-8.
    "coerced-sterilization-indigenous": ["hope_for_wellness", "mmiwg_crisis_line", "helpline_988"],
    "tainted-blood-krever": ["helpline_988"],
    "early-hiv-aids": ["helpline_988"],
}

# Fallbacks for a sensitive surface that has no specific topic mapping. The Gaps care note (about
# harm to Indigenous people) uses indigenous_sensitive.
DEFAULT_RESOURCES: dict[str, list[str]] = {
    "indigenous_sensitive": ["helpline_988", "hope_for_wellness"],
    "other_sensitive": ["helpline_988"],
}


def resource(key: str) -> dict:
    """A copy of one resource, so callers never mutate the canonical dict."""
    return dict(RESOURCES[key])


def resources_for_topics(topics) -> list[dict]:
    """Ordered, de-duplicated resource objects for the given detection topics: topic order first,
    then each topic's own display order. A topic with no mapping contributes nothing."""
    out: list[dict] = []
    seen: set[str] = set()
    for t in topics:
        for k in TOPIC_RESOURCES.get(t, []):
            if k not in seen:
                seen.add(k)
                out.append(resource(k))
    return out


def default_resources(kind: str) -> list[dict]:
    return [resource(k) for k in DEFAULT_RESOURCES.get(kind, [])]


def serialized() -> dict:
    """The full crisis payload the API serves so static surfaces can render the right resources
    without an /ask: the resources, the topic map, and the resolved default lists."""
    return {
        "resources": {k: dict(v) for k, v in RESOURCES.items()},
        "topic_resources": {t: list(ks) for t, ks in TOPIC_RESOURCES.items()},
        "defaults": {kind: default_resources(kind) for kind in DEFAULT_RESOURCES},
    }
