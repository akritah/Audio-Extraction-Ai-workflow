from fastapi import APIRouter, Query
from db.setup import get_connection
from services.search import search as semantic_search

router = APIRouter()


@router.get("/")
def search(q: str = Query(..., min_length=2), top_k: int = 10):
    """
    Semantic search over all indexed meetings.
    Returns matching chunks with meeting metadata.
    """
    hits = semantic_search(q, top_k=top_k)

    # enrich each hit with meeting title/filename
    conn  = get_connection()
    cache = {}
    for h in hits:
        mid = h.get("meeting_id")
        if mid and mid not in cache:
            row = conn.execute(
                "SELECT filename, title, created_at FROM meetings WHERE id=?", (mid,)
            ).fetchone()
            cache[mid] = dict(row) if row else {}
        h["meeting"] = cache.get(mid, {})

    conn.close()
    return hits
