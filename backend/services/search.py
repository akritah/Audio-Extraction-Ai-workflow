import uuid
from sentence_transformers import SentenceTransformer
from db.setup import get_collection

# all-MiniLM-L6-v2 is small (80MB) and fast — good for CPU-only deployment
# For better accuracy use: all-mpnet-base-v2 (420MB)
# For multilingual: paraphrase-multilingual-mpnet-base-v2
_embedder = None

CHUNK_SIZE = 300  # characters per chunk


def get_embedder():
    global _embedder
    if _embedder is None:
        _embedder = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
    return _embedder


def chunk_text(text: str) -> list:
    """Split transcript into overlapping chunks for better retrieval coverage."""
    words    = text.split()
    chunks   = []
    step     = CHUNK_SIZE // 2   # 50% overlap between chunks
    chunk_words = CHUNK_SIZE // 5

    for i in range(0, len(words), step):
        chunk = " ".join(words[i:i + chunk_words])
        if chunk:
            chunks.append(chunk)

    return chunks


def index_meeting(meeting_id: int, transcript: str, summary: str, tasks: list):
    """Store meeting text chunks in ChromaDB for later retrieval."""
    col      = get_collection()
    embedder = get_embedder()

    all_text = []

    # index transcript chunks
    for chunk in chunk_text(transcript):
        all_text.append({"text": chunk, "type": "transcript"})

    # index summary as one block
    if summary:
        all_text.append({"text": summary, "type": "summary"})

    # index each task individually so task-specific queries work well
    for t in tasks:
        task_str = f"Task: {t.get('task','')} Owner: {t.get('owner','')} Deadline: {t.get('deadline','')}"
        all_text.append({"text": task_str, "type": "task"})

    if not all_text:
        return

    texts      = [item["text"]  for item in all_text]
    embeddings = embedder.encode(texts, show_progress_bar=False).tolist()

    col.add(
        ids        =[str(uuid.uuid4()) for _ in texts],
        embeddings =embeddings,
        documents  =texts,
        metadatas  =[{"meeting_id": meeting_id, "type": item["type"]} for item in all_text],
    )


def search(query: str, top_k: int = 10) -> list:
    """Return top_k most relevant chunks for the natural language query."""
    col      = get_collection()
    embedder = get_embedder()

    vec = embedder.encode([query]).tolist()

    results = col.query(
        query_embeddings=vec,
        n_results=top_k,
        include=["documents", "metadatas", "distances"],
    )

    out = []
    if results and results["documents"]:
        for doc, meta, dist in zip(
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0],
        ):
            out.append({
                "text":       doc,
                "meeting_id": meta.get("meeting_id"),
                "type":       meta.get("type"),
                "score":      round(1 - dist, 4),  # cosine similarity
            })

    return out
