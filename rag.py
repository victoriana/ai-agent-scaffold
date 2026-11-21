# rag.py : RBAC-Filtered Policy Search + Threshold Fallback
# Uses token/keyword overlap scoring (no brittle hardcoded 3D vectors), filters by allowed_roles before scoring, and falls back cleanly when top_score < min_score_threshold.

import json
from dataclasses import dataclass
from pathlib import Path

from ingest import run_ingestion


@dataclass
class PolicyHit:
    chunk_id: str
    doc_id: str
    section: str
    text: str
    score: float


STOPWORDS = {
    "the",
    "a",
    "an",
    "is",
    "are",
    "for",
    "to",
    "of",
    "in",
    "on",
    "my",
    "i",
    "what",
    "how",
    "do",
}


def _tokenize(text: str) -> set[str]:
    cleaned = "".join(ch.lower() if ch.isalnum() or ch in {"-", "_"} else " " for ch in text)
    return {tok for tok in cleaned.split() if len(tok) > 1 and tok not in STOPWORDS}


def load_policy_chunks(index_path: str = "policy_index.json") -> list[dict]:
    """Loads ingested policy chunks from disk, auto-seeding via ingest.py if absent."""
    path = Path(index_path)
    if not path.exists():
        ingested = run_ingestion(output_path=index_path)
        return [
            {
                "chunk_id": item.chunk_id,
                "doc_id": item.doc_id,
                "section": item.section,
                "text": item.text,
                "allowed_roles": item.allowed_roles,
            }
            for item in ingested
        ]
    return json.loads(path.read_text(encoding="utf-8"))


def search_policies(
    query: str,
    user_role: str,
    top_k: int = 3,
    min_score: float = 0.25,
    index_path: str = "policy_index.json",
) -> tuple[list[PolicyHit], bool]:
    """
    Retrieves authorized policy chunks for `user_role` before scoring.
    Returns `(hits, fallback_triggered)`.
    """
    chunks = load_policy_chunks(index_path=index_path)
    authorized = [c for c in chunks if user_role in c.get("allowed_roles", [])]
    if not authorized:
        return [], True

    q_tokens = _tokenize(query)
    if not q_tokens:
        return [], True

    scored: list[PolicyHit] = []
    q_lower = query.lower()

    for chunk in authorized:
        doc_id = chunk["doc_id"]
        section = chunk["section"]
        text = chunk["text"]
        doc_tokens = _tokenize(f"{doc_id} {section} {text}")

        overlap = len(q_tokens & doc_tokens)
        score = round(overlap / len(q_tokens), 3)

        if doc_id.lower() in q_lower:
            score = min(1.0, round(score + 0.5, 3))

        if score > 0:
            scored.append(
                PolicyHit(
                    chunk_id=chunk["chunk_id"],
                    doc_id=doc_id,
                    section=section,
                    text=text,
                    score=score,
                )
            )

    scored.sort(key=lambda h: h.score, reverse=True)
    hits = scored[:top_k]

    if not hits or hits[0].score < min_score:
        return [], True

    return hits, False
