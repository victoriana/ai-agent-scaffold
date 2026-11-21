# rag.py : RBAC-Filtered Policy Search + Threshold Fallback
# Uses token/keyword overlap scoring (no brittle hardcoded 3D vectors), filters by allowed_roles before scoring, and falls back cleanly when top_score < min_score_threshold.

from dataclasses import dataclass

@dataclass
class PolicyDoc:
    doc_id: str
    section: str
    text: str
    allowed_roles: list[str]


@dataclass
class PolicyHit:
    doc_id: str
    section: str
    text: str
    score: float


POLICIES: list[PolicyDoc] = [
    PolicyDoc(
        doc_id="POL-PTO-01",
        section="Paid Time Off",
        text="Full-time employees accrue 15 days of PTO per year and must submit requests at least 14 days in advance.",
        allowed_roles=["employee", "manager", "hr_admin"],
    ),
    PolicyDoc(
        doc_id="POL-TRV-04",
        section="Travel & Expenses",
        text="Travel meals are reimbursed up to $75 per day with itemized receipts submitted within 10 business days.",
        allowed_roles=["employee", "manager", "hr_admin"],
    ),
    PolicyDoc(
        doc_id="POL-MGR-09",
        section="Spot Bonuses",
        text="Managers may approve spot bonuses up to $1,000 without VP sign-off.",
        allowed_roles=["manager", "hr_admin"],
    ),
]

STOPWORDS = {"the", "a", "an", "is", "are", "for", "to", "of", "in", "on", "my", "i", "what", "how", "do"}


def _tokenize(text: str) -> set[str]:
    cleaned = "".join(ch.lower() if ch.isalnum() or ch in {"-", "_"} else " " for ch in text)
    return {tok for tok in cleaned.split() if len(tok) > 1 and tok not in STOPWORDS}


def search_policies(
    query: str,
    user_role: str,
    top_k: int = 3,
    min_score: float = 0.25,
) -> tuple[list[PolicyHit], bool]:
    """Returns (hits, fallback_triggered). Enforces RBAC before scoring."""
    authorized = [doc for doc in POLICIES if user_role in doc.allowed_roles]
    if not authorized:
        return [], True

    q_tokens = _tokenize(query)
    if not q_tokens:
        return [], True

    scored: list[PolicyHit] = []
    for doc in authorized:
        doc_tokens = _tokenize(f"{doc.doc_id} {doc.section} {doc.text}")
        overlap = len(q_tokens & doc_tokens)
        score = round(overlap / len(q_tokens), 3)

        # Exact policy ID match boost
        if doc.doc_id.lower() in query.lower():
            score = min(1.0, round(score + 0.5, 3))

        if score > 0:
            scored.append(PolicyHit(doc_id=doc.doc_id, section=doc.section, text=doc.text, score=score))

    scored.sort(key=lambda h: h.score, reverse=True)
    hits = scored[:top_k]

    if not hits or hits[0].score < min_score:
        return [], True

    return hits, False
