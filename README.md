# ProjectPilot AI — Capstone Scaffold

Scoped MVP of the full ProjectPilot AI vision: an engineering workflow
orchestrator (not a chatbot) with real LangGraph conditional routing,
multi-capability fan-out, RAG, a live GitHub integration, artifact
generation, and — the differentiator most capstones skip — a working
automated evaluation layer (golden dataset + LLM-as-judge).

## What's here

```
app/
  state.py                shared LangGraph state schema
  graph/
    scope_guard.py         rejects out-of-scope / adversarial requests
    router.py               goal interpreter + capability router (supports multi-capability fan-out)
    agent.py                 final reasoning node (+ reject node)
    build.py                  wires everything into the compiled LangGraph
  capabilities/
    knowledge.py             RAG (ChromaDB + local embeddings)
    ingest.py                 loads data/sample_docs/ into ChromaDB
    github_intel.py           GitHub repo analysis + deterministic health score
    artifact.py               README/diagram generation
  memory/store.py            simple per-session conversation memory
  eval/
    golden_dataset.py         14 seeded test cases (grow to 20)
    judge.py                   LLM-as-judge, scoped to this agent's dimensions
    run_eval.py                 runs golden set -> agent -> judge -> eval_results.json
  main.py                    FastAPI app (POST /query)
frontend/streamlit_app.py  demo UI
data/sample_docs/          placeholder docs for RAG — replace with your real ones
```

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env        # fill in ANTHROPIC_API_KEY, GITHUB_TOKEN, GITHUB_REPO
python -m app.capabilities.ingest      # loads data/sample_docs/ into ChromaDB
uvicorn app.main:app --reload          # terminal 1: backend on :8000
streamlit run frontend/streamlit_app.py  # terminal 2: demo UI
```

**Important:** activate `.venv` in *both* terminals (backend and Streamlit are
separate processes) — otherwise the second one will silently fall back to
your system Python and complain about missing packages.

GitHub token: https://github.com/settings/tokens (classic, `public_repo` scope is enough, free).

## Running the eval pipeline

```bash
python -m app.eval.golden_dataset   # validate + write golden_dataset.json
python -m app.eval.run_eval         # scores every case, writes eval_results.json
```

## Build order (2 weeks)

1. **Days 1-2** — Get this scaffold running end-to-end with placeholder data.
   Confirm the graph actually fans out (add a print/log in each capability
   node and watch multi-capability queries hit more than one).
2. **Days 3-5** — Replace `data/sample_docs/` with your real project docs,
   tune the RAG prompt in `knowledge.py`, verify citations are accurate.
3. **Days 6-8** — Point `GITHUB_REPO` at your real capstone repo, verify the
   health score and blocker detection against real issues/labels.
4. **Days 9-10** — Test multi-capability queries ("are we ready for
   submission?"), tune `artifact.py` for README/diagram generation quality.
5. **Days 11-12** — Grow `golden_dataset.py` to 20 items using YOUR real
   docs/repo, run `run_eval.py`, iterate on prompts until scores are solid,
   note any interesting failures for your demo narrative.
6. **Day 13** — Polish the Streamlit UI, wire memory into multi-turn demo
   flows.
7. **Day 14** — Buffer + record/rehearse the demo, write the demo script
   (what to type, in what order, to show routing, RAG, GitHub, artifact
   generation, AND the eval report).

## Notes / things to sanity-check as you build

- `route_condition` in `router.py` returns a **list** of capability node
  names for fan-out. Confirm your installed `langgraph` version supports
  returning a list from a conditional edge function (it does as of the
  pinned version in `requirements.txt`); if not, switch to LangGraph's
  `Send` API for the same effect.
- The GitHub health score is intentionally **deterministic**, not
  LLM-judged — matches the Session 10 principle that exact/loggable things
  (issue counts, commit recency) don't need a judge, only genuinely
  subjective calls do.
- Everything here uses free tiers: local embeddings (sentence-transformers,
  no API cost), GitHub REST API (free, 5k req/hr with a token), Mermaid
  rendering is client-side. Only the Anthropic API costs anything, and only
  per call.
