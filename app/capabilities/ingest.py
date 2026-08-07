"""
One-off script: chunk and load a project's docs into its OWN ChromaDB
collection. Run this once per project (and again whenever you update that
project's docs) with:

    python -m app.capabilities.ingest                  # ingests the currently active project
    python -m app.capabilities.ingest gesture_control   # ingests a specific project by id
"""
import os
import sys
import glob

from app.capabilities.knowledge import get_collection
from app.project_config import list_projects, get_active_project

SAMPLE_DOCS_ROOT = os.path.join(os.path.dirname(__file__), "..", "..", "data", "sample_docs")
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


def ingest(project_id: str):
    projects = list_projects()
    if project_id not in projects:
        print(f"Unknown project id '{project_id}'. Known: {list(projects.keys())}")
        return

    project = projects[project_id]
    docs_dir = os.path.join(SAMPLE_DOCS_ROOT, project["docs_folder"])
    collection = get_collection(project_id)

    files = glob.glob(os.path.join(docs_dir, "*.md")) + glob.glob(os.path.join(docs_dir, "*.txt"))
    if not files:
        print(f"No docs found in {docs_dir} for project '{project_id}' — add docs there first.")
        return

    ids, documents, metadatas = [], [], []
    for path in files:
        source = os.path.basename(path)
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
        for i, chunk in enumerate(chunk_text(text)):
            ids.append(f"{project_id}-{source}-{i}")
            documents.append(chunk)
            metadatas.append({"source": source})

    collection.upsert(ids=ids, documents=documents, metadatas=metadatas)
    print(f"Ingested {len(documents)} chunks from {len(files)} files for '{project['label']}' "
          f"({[os.path.basename(f) for f in files]})")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        target_id = sys.argv[1]
    else:
        target_id = get_active_project()["id"]
    ingest(target_id)
