# Pseudo-code for your mental model
# 1. Load docs (PDF/Markdown)
# 2. Chunk using RecursiveCharacterTextSplitter
# 3. Embed using Vertex AI / OpenAI embeddings
# 4. Store in Vector DB (Pinecone/FAISS/Chroma)
# 5. Retrieve top-k chunks based on query similarity

# Policy Search with RBAC Pre-Filtering, Hybrid Search, Reranking & "I don't know" Threshold

import math
from dataclasses import dataclass


@dataclass
class PolicyChunk:
    chunk_id: str
    doc_id: str
    page: int
    text: str
    vector: list[float]
    allowed_roles: list[str]


@dataclass
class SearchHit:
    chunk_id: str
    doc_id: str
    page: int
    text: str
    score: float


# Simulated pgvector table: employee_policies_text_embed_004
POLICY_STORE: list[PolicyChunk] = [
    PolicyChunk(
        chunk_id="POL-PTO-01_p2_c0",
        doc_id="POL-PTO-01",
        page=2,
        text="Full-time employees accrue 15 days of PTO annually and must submit requests at least 14 days in advance via the HR portal.",
        vector=[0.9, 0.1, 0.0],
        allowed_roles=["employee", "manager", "hr_admin"],
    ),
    PolicyChunk(
        chunk_id="POL-TRV-04_p5_c1",
        doc_id="POL-TRV-04",
        page=5,
        text="Corporate travel meals are reimbursed up to $75 per day with itemized receipts submitted within 10 business days.",
        vector=[0.1, 0.9, 0.0],
        allowed_roles=["employee", "manager", "hr_admin"],
    ),
    PolicyChunk(
        chunk_id="POL-MGR-09_p1_c0",
        doc_id="POL-MGR-09",
        page=1,
        text="Managers may approve discretionary spot bonuses up to $1,000 without VP sign-off.",
        vector=[0.0, 0.1, 0.9],
        allowed_roles=["manager", "hr_admin"],
    ),
]


def embed_text(text: str) -> list[float]:
    """Simulates calling a pinned embedding model (text-embedding-004)."""
    q = text.lower()
    if any(k in q for k in ["pto", "vacation", "time off", "leave"]):
        return [0.9, 0.1, 0.0]
    if any(k in q for k in ["travel", "meal", "reimburse", "expense"]):
        return [0.1, 0.9, 0.0]
    if any(k in q for k in ["bonus", "spot", "manager", "approve"]):
        return [0.0, 0.1, 0.9]
    return [0.0, 0.0, 0.0]


def cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    return dot / (norm_a * norm_b) if norm_a and norm_b else 0.0


def bm25_keyword_score(query: str, text: str) -> float:
    clean = lambda s: set(s.lower().replace("?", "").replace(".", "").replace(",", "").split())
    q_terms, t_terms = clean(query), clean(text)
    return len(q_terms & t_terms) / max(len(q_terms), 1)


def rerank_score(query: str, text: str, hybrid_score: float) -> float:
    # Boost if exact policy code (e.g., POL-PTO-01) appears in query
    code_match = any(tok.startswith("pol-") and tok in text.lower() for tok in query.lower().split())
    return min(1.0, hybrid_score + (0.25 if code_match else 0.0))


def search_policies(
    query: str,
    user_role: str,
    top_k: int = 3,
    min_score_threshold: float = 0.65,
) -> tuple[list[SearchHit], bool]:
    """
    Retrieves policy chunks with RBAC pre-filtering, hybrid search, reranking,
    and a score-threshold 'I don't know' fallback.
    """
    # 1. Pre-retrieval RBAC metadata filter (BEFORE similarity scoring)
    authorized = [c for c in POLICY_STORE if user_role in c.allowed_roles]
    if not authorized:
        return [], True

    query_vec = embed_text(query)

    # 2. Hybrid search (70% dense semantic vector + 30% sparse BM25 keywords)
    candidates: list[tuple[PolicyChunk, float]] = []
    for chunk in authorized:
        vec_score = cosine_similarity(query_vec, chunk.vector)
        kw_score = bm25_keyword_score(query, chunk.text)
        candidates.append((chunk, (0.7 * vec_score) + (0.3 * kw_score)))

    candidates.sort(key=lambda item: item[1], reverse=True)

    # 3. Cross-encoder reranking proxy
    reranked = [
        SearchHit(
            chunk_id=chunk.chunk_id,
            doc_id=chunk.doc_id,
            page=chunk.page,
            text=chunk.text,
            score=round(rerank_score(query, chunk.text, score), 3),
        )
        for chunk, score in candidates[: top_k * 2]
    ]
    reranked.sort(key=lambda h: h.score, reverse=True)
    final_hits = reranked[:top_k]

    # 4. Score threshold safety gate ("I don't know" fallback)
    if not final_hits or final_hits[0].score < min_score_threshold:
        return [], True

    return final_hits, False

