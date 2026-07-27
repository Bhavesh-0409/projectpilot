"""
One-off script: chunk and load the docs in data/sample_docs/ into ChromaDB.
Run this once (and again whenever you update your docs) with:
    python -m app.capabilities.ingest
"""
import os
import glob
from app.capabilities.knowledge import get_collection

SAMPLE_DOCS_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data", "sample_docs")
CHUNK_SIZE = 800   # characters; simple fixed-size chunking is fine for a capstone-scale doc set
CHUNK_OVERLAP = 100


def chunk_text(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP):
    chunks = []
    start = 0
    while start < len(text):
        end = start + size
        chunks.append(text[start:end])
        start = end - overlap
    return chunks


def ingest():
    collection = get_collection()
    files = glob.glob(os.path.join(SAMPLE_DOCS_DIR, "*.md")) + \
            glob.glob(os.path.join(SAMPLE_DOCS_DIR, "*.txt"))

    if not files:
        print(f"No docs found in {SAMPLE_DOCS_DIR} — add your README/SRS/design docs there first.")
        return

    ids, documents, metadatas = [], [], []
    for path in files:
        source = os.path.basename(path)
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
        for i, chunk in enumerate(chunk_text(text)):
            ids.append(f"{source}-{i}")
            documents.append(chunk)
            metadatas.append({"source": source})

    # upsert so re-running is idempotent
    collection.upsert(ids=ids, documents=documents, metadatas=metadatas)
    print(f"Ingested {len(documents)} chunks from {len(files)} files: {[os.path.basename(f) for f in files]}")


if __name__ == "__main__":
    ingest()
