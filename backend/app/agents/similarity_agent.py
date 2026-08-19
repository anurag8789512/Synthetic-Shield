"""
Similarity Agent: uses ChromaDB to find claims with similar narratives.
Uses a simple hash-based embedding function that works fully offline.
Writes similarity score back to claims.narrative_similarity_score for SQL analytics.
"""
import hashlib
import math
from collections import Counter

import chromadb
from sqlalchemy.orm import Session as DBSession

from app.models import Claim

DIMS = 384


def _embed_text(text: str) -> list[float]:
    words = text.lower().split()
    word_counts = Counter(words)
    vec = [0.0] * DIMS
    for word, count in word_counts.items():
        h = int(hashlib.md5(word.encode()).hexdigest(), 16)
        idx = h % DIMS
        vec[idx] += count * (1.0 / math.log2(len(word) + 2))
    magnitude = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / magnitude for v in vec]


_client = None
_collection = None


def _get_collection():
    global _client, _collection
    if _collection is None:
        _client = chromadb.Client()
        _collection = _client.get_or_create_collection(
            name="claim_narratives",
            metadata={"hnsw:space": "cosine"},
        )
    return _collection


def index_claim(claim_id: int, description: str, outcome: str = "unknown") -> None:
    """Add or update a claim narrative in the Chroma collection."""
    _get_collection().upsert(
        ids=[str(claim_id)],
        embeddings=[_embed_text(description)],
        documents=[description],
        metadatas=[{"claim_id": claim_id, "outcome": outcome}],
    )


def find_similar(description: str, exclude_claim_id: int | None = None, top_k: int = 5) -> list[dict]:
    """Find claims with similar narratives. Returns list of matches with scores."""
    results = _get_collection().query(
        query_embeddings=[_embed_text(description)],
        n_results=top_k + 1,  # Extra in case we need to exclude self
    )

    matches = []
    if results and results["ids"] and results["ids"][0]:
        for i, cid in enumerate(results["ids"][0]):
            if exclude_claim_id and str(exclude_claim_id) == cid:
                continue
            if len(matches) >= top_k:
                break

            distance = results["distances"][0][i] if results["distances"] else 1.0
            similarity = round((1 - distance) * 100, 1)  # Convert cosine distance to similarity %
            metadata = results["metadatas"][0][i] if results["metadatas"] else {}

            matches.append({
                "claim_id": int(cid),
                "similarity_score": similarity,
                "outcome": metadata.get("outcome", "unknown"),
                "document": results["documents"][0][i] if results["documents"] else "",
            })

    return matches


def process_claim_similarity(claim_id: int, db: DBSession) -> float | None:
    """Index a claim and find its similarity to existing claims. Returns highest similarity score."""
    claim = db.query(Claim).filter(Claim.id == claim_id).first()
    if not claim or not claim.accident_description:
        return None

    # Determine outcome label
    outcome = "unknown"
    if claim.status in ("siu_confirmed_fraud",):
        outcome = "fraud"
    elif claim.status in ("auto_approved", "siu_cleared"):
        outcome = "legitimate"

    # Index this claim
    index_claim(claim_id, claim.accident_description, outcome)

    # Query for similar claims (excluding self)
    matches = find_similar(claim.accident_description, exclude_claim_id=claim_id, top_k=3)

    # Write the highest similarity score back to SQLite
    if matches:
        top_score = max(m["similarity_score"] for m in matches)
        claim.narrative_similarity_score = top_score
        db.commit()
        return top_score

    claim.narrative_similarity_score = 0.0
    db.commit()
    return 0.0


def reindex_all_claims(db: DBSession) -> int:
    """Re-index all claims into Chroma. Returns count."""
    claims = db.query(Claim).filter(Claim.accident_description.isnot(None)).all()
    for claim in claims:
        outcome = "unknown"
        if claim.status in ("siu_confirmed_fraud",):
            outcome = "fraud"
        elif claim.status in ("auto_approved", "siu_cleared"):
            outcome = "legitimate"
        index_claim(claim.id, claim.accident_description, outcome)
    return len(claims)
