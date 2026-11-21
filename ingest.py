# ingest.py — Lightweight Offline Ingestion Pipeline

import json
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass
class IngestedChunk:
    chunk_id: str
    doc_id: str
    section: str
    text: str
    allowed_roles: list[str]


RAW_POLICIES = [
    {
        "doc_id": "POL-PTO-01",
        "section": "Paid Time Off",
        "text": "Full-time employees accrue 15 days of PTO per year and must submit requests at least 14 days in advance.",
        "allowed_roles": ["employee", "manager", "hr_admin"],
    },
    {
        "doc_id": "POL-TRV-04",
        "section": "Travel & Expenses",
        "text": "Travel meals are reimbursed up to $75 per day with itemized receipts submitted within 10 business days.",
        "allowed_roles": ["employee", "manager", "hr_admin"],
    },
    {
        "doc_id": "POL-MGR-09",
        "section": "Spot Bonuses",
        "text": "Managers may approve spot bonuses up to $1,000 without VP sign-off.",
        "allowed_roles": ["manager", "hr_admin"],
    },
]


def chunk_text(text: str, chunk_size: int = 120, overlap: int = 20) -> list[str]:
    """Splits text into overlapping character windows (swap for token splitter in prod)."""
    if chunk_size <= overlap:
        raise ValueError("chunk_size must be greater than overlap")
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        piece = text[start:end].strip()
        if piece:
            chunks.append(piece)
        if end >= len(text):
            break
        start = end - overlap
    return chunks


def run_ingestion(
    records: list[dict] = RAW_POLICIES,
    output_path: str = "policy_index.json",
    chunk_size: int = 120,
    overlap: int = 20,
) -> list[IngestedChunk]:
    """Offline step: chunk policies, attach RBAC metadata, and persist index."""
    indexed: list[IngestedChunk] = []
    for rec in records:
        pieces = chunk_text(rec["text"], chunk_size=chunk_size, overlap=overlap)
        for idx, piece in enumerate(pieces):
            indexed.append(
                IngestedChunk(
                    chunk_id=f"{rec['doc_id']}_c{idx}",
                    doc_id=rec["doc_id"],
                    section=rec["section"],
                    text=piece,
                    allowed_roles=rec["allowed_roles"],
                )
            )

    Path(output_path).write_text(
        json.dumps([asdict(item) for item in indexed], indent=2),
        encoding="utf-8",
    )
    return indexed


if __name__ == "__main__":
    created = run_ingestion()
    print(f"Ingested {len(created)} chunks into policy_index.json")
