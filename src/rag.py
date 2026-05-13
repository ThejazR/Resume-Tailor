"""Retrieval against the resume collection in Qdrant."""
from functools import lru_cache

from qdrant_client import QdrantClient
from sentence_transformers import SentenceTransformer

from src.config import COLLECTION_NAME, EMBED_MODEL, QDRANT_HOST, QDRANT_PORT


@lru_cache(maxsize=1)
def _encoder() -> SentenceTransformer:
    return SentenceTransformer(EMBED_MODEL)


@lru_cache(maxsize=1)
def _client() -> QdrantClient:
    return QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)


def retrieve(query: str, k: int = 6) -> list[str]:
    """Return the top-k most relevant resume chunks for the query."""
    vector = _encoder().encode(query).tolist()
    hits = _client().query_points(
        collection_name=COLLECTION_NAME,
        query=vector,
        limit=k,
    ).points
    return [h.payload["text"] for h in hits if h.payload and "text" in h.payload]
