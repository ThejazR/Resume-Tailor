"""One-shot: read resume.pdf, chunk, embed, upsert into Qdrant.

Run: python -m src.ingest
"""
import uuid

from pypdf import PdfReader
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams
from sentence_transformers import SentenceTransformer

from src.config import (
    COLLECTION_NAME,
    EMBED_DIM,
    EMBED_MODEL,
    QDRANT_HOST,
    QDRANT_PORT,
    RESUME_PDF,
)


def split_text(text: str, chunk_size: int = 500) -> list[str]:
    chunks: list[str] = []
    start = 0
    while start < len(text):
        chunks.append(text[start : start + chunk_size])
        start += chunk_size
    return chunks


def main() -> None:
    if not RESUME_PDF.exists():
        raise SystemExit(f"resume.pdf not found at {RESUME_PDF}")

    print(f"Loading embedding model ({EMBED_MODEL})...")
    encoder = SentenceTransformer(EMBED_MODEL)

    print(f"Connecting to Qdrant at {QDRANT_HOST}:{QDRANT_PORT}...")
    qdrant = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)

    # Recreate collection so re-runs reflect the latest resume.
    print(f"Recreating collection '{COLLECTION_NAME}'...")
    if qdrant.collection_exists(COLLECTION_NAME):
        qdrant.delete_collection(COLLECTION_NAME)
    qdrant.create_collection(
        collection_name=COLLECTION_NAME,
        vectors_config=VectorParams(size=EMBED_DIM, distance=Distance.COSINE),
    )

    print(f"Reading {RESUME_PDF.name}...")
    reader = PdfReader(str(RESUME_PDF))
    text = ""
    for page in reader.pages:
        extracted = page.extract_text()
        if extracted:
            text += extracted + "\n"

    chunks = split_text(text)
    print(f"Created {len(chunks)} chunks")

    print("Generating embeddings...")
    vectors = encoder.encode(chunks).tolist()

    points = [
        PointStruct(
            id=str(uuid.uuid4()),
            vector=vectors[i],
            payload={"text": chunk},
        )
        for i, chunk in enumerate(chunks)
    ]

    print("Upserting into Qdrant...")
    qdrant.upsert(collection_name=COLLECTION_NAME, points=points)
    print(f"Stored {len(points)} chunks in Qdrant.")


if __name__ == "__main__":
    main()
