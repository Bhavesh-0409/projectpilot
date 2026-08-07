# ProjectPilot AI

## What it is

ProjectPilot AI is an engineering workflow orchestration platform for
software teams, built as a ServiceNow AI Bootcamp capstone (Path B - Build
Your Own). It is not a chatbot: instead of only answering questions, it
interprets a user's goal, decides which engineering capability is required,
invokes one or more tools, reasons over the collected information, and
either answers, acts, or generates an engineering artifact.

## Problem it solves

Software teams constantly switch between GitHub, documentation, project
specs, and issue trackers to answer basic questions about their own
project's state. ProjectPilot AI unifies these behind one interface that
reasons across all of them at once.

## Capabilities (v1)

### 1. Knowledge Management
Retrieval-augmented question answering over the project's own
documentation (this README, the architecture doc, the requirements doc).
Uses ChromaDB with local `sentence-transformers` embeddings
(`all-MiniLM-L6-v2`) - no external embedding API required. Every answer is
grounded in retrieved chunks and cites its source document; if the answer
isn't in the docs, the agent says so rather than inventing one.

### 2. Project Intelligence
Live analysis of the project's GitHub repository via the GitHub REST API.
Reports open issue count, days since last commit, and blocker-labeled
issues (labels: `blocker`, `bug`, `critical`), and computes a deterministic
engineering health score out of 100 (see architecture.md for the formula).
This is deliberately NOT an LLM judgment call - it's exact and loggable,
so a rule-based score is used instead of an LLM opinion. This same
capability can also read a single source file under `app/` or `frontend/`
when given the exact repo-relative path, so the agent can compare code
against documentation. It does not support full-text codebase search,
directory browsing, or guessing likely paths: if the exact path is not
known, the agent asks the user for it first.

### 3. Engineering Design
Generates engineering artifacts - README sections, Mermaid architecture or
flow diagrams, project summaries - using whatever context the other two
capabilities gathered in that same turn. Artifacts are grounded in real
retrieved/analyzed data, not generated from a blank prompt.

## Out of scope (v1)

The following are explicitly NOT supported and requests for them should be
declined by the scope guard rather than attempted: calendar/meeting
scheduling, creating or modifying GitHub issues or pull requests, sending
notifications or emails, executing arbitrary code, full-text search across
the codebase, reading files outside the allowed `app/` and `frontend/`
source directories, and any action that would write to an external system.
These are documented future-work items, not current features.

## Tech stack

- **Orchestration:** LangGraph (Python), conditional routing with
  multi-capability fan-out
- **Backend:** FastAPI
- **LLM:** Claude (Anthropic API) - used by the scope guard, router, RAG
  answer synthesis, artifact generation, and final agent reasoning
- **Retrieval:** ChromaDB (local, persistent) + sentence-transformers
  (local embeddings, free, no API cost)
- **External data:** GitHub REST API (free tier, 5,000 requests/hour with
  a personal access token)
- **Frontend:** Streamlit (chat interface for demo purposes)
- **Evaluation:** custom golden dataset + LLM-as-judge pipeline (see
  requirements.md, section "Evaluation Requirements")

## How a request flows through the system

A user request first passes through a scope guard, which checks whether
the request is something the agent can actually do and rejects prompt
injection or requests for unsupported actions (e.g. "delete my issues").
If approved, a goal interpreter/router decides which capability node(s)
the request needs - a single query can require more than one capability at
once (for example, "are we ready for submission?" requires both Knowledge
Management and Project Intelligence). The relevant capability node(s) run,
their outputs are combined by a final reasoning ("agent") node, and the
response is returned along with a full trace of every decision made along
the way.
