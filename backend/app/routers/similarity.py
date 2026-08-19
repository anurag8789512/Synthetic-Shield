"""
Similarity search endpoints for finding claims with similar narratives.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session as DBSession

from app.database import get_db
from app.models import Claim
from app.agents.similarity_agent import find_similar, reindex_all_claims

router = APIRouter(prefix="/similarity", tags=["similarity"])


@router.get("/search")
def search_similar(description: str, top_k: int = 5):
    """Find claims with similar narratives to the given description."""
    matches = find_similar(description, top_k=top_k)
    return {"query": description[:100], "matches": matches}


@router.get("/claim/{claim_id}")
def get_claim_similarities(claim_id: int, db: DBSession = Depends(get_db)):
    """Find claims similar to an existing claim."""
    claim = db.query(Claim).filter(Claim.id == claim_id).first()
    if not claim:
        raise HTTPException(status_code=404, detail="Claim not found.")
    if not claim.accident_description:
        return {"claim_id": claim_id, "matches": [], "message": "No narrative to search."}

    matches = find_similar(claim.accident_description, exclude_claim_id=claim_id, top_k=5)

    # Enrich with claim numbers
    for m in matches:
        c = db.query(Claim).filter(Claim.id == m["claim_id"]).first()
        if c:
            m["claim_number"] = c.claim_number
            m["status"] = c.status
            m["fraud_score"] = c.fraud_confidence_score

    return {
        "claim_id": claim_id,
        "claim_number": claim.claim_number,
        "narrative_similarity_score": claim.narrative_similarity_score,
        "matches": matches,
    }


@router.post("/reindex")
def reindex(db: DBSession = Depends(get_db)):
    """Re-index all existing claims into Chroma."""
    try:
        count = reindex_all_claims(db)
        # Verify the collection has data
        from app.agents.similarity_agent import _get_collection
        coll = _get_collection()
        coll_count = coll.count()
        return {"reindexed": count, "collection_count": coll_count}
    except Exception as e:
        import traceback
        return {"error": str(e), "traceback": traceback.format_exc()}
