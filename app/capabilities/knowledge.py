"""
Knowledge Management capability — RAG over project docs using ChromaDB
with local sentence-transformers embeddings (free, no API cost, runs
on CPU). Grounded answers always carry citations back to the source
chunk so the eval judge can check faithfulness.

Each project (see project_config.py) gets its OWN ChromaDB collection,
named after the project id, so docs from different projects never mix
into the same retrieval pool — critical now that multiple projects can
be analyzed by the same running system.
"""
import os
import chromadb
from chromadb.utils import embedding_functions
from anthropic import Anthropic

from app.project_config import get_active_project

CHROMA_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "data", "chroma_db")

_embedding_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
    model_name="all-MiniLM-L6-v2"
)


def get_collection(project_id: str):
    client = chromadb.PersistentClient(path=CHROMA_PATH)
    return client.get_or_create_collection(
        name=f"project_docs__{project_id}", embedding_function=_embedding_fn
    )


def knowledge_node(state: dict) -> dict:
    active_project = get_active_project()
    collection = get_collection(active_project["id"])
    query = state["user_query"]

    results = collection.query(query_texts=[query], n_results=4)
    docs = results.get("documents", [[]])[0]
    metas = results.get("metadatas", [[]])[0]

    if not docs:
        answer = (
            f"I don't have any documentation ingested yet for "
            f"'{active_project['label']}', so I can't ground an answer. "
            f"Run the ingest script for this project first."
        )
        citations = []
    else:
        context = "\n\n".join(
            f"[Source: {m.get('source', 'unknown')}]\n{d}" for d, m in zip(docs, metas)
        )
        prompt = f"""Answer the user's question using ONLY the context below. If the
context doesn't contain the answer, say so explicitly — never invent facts about
the project.

Context:
{context}

Question: {query}

Answer, then on a new line list the sources you used as "Sources: ..."."""

        client = Anthropic()
        resp = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=500,
            messages=[{"role": "user", "content": prompt}],
        )
        answer = resp.content[0].text.strip()
        citations = [m.get("source", "unknown") for m in metas]

    return {
        "knowledge_result": {"answer": answer, "citations": citations},
        "trace": [{"node": "knowledge", "project": active_project["id"], "citations": citations}],
    }
