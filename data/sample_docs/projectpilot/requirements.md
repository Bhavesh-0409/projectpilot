# Requirements

## Functional requirements

### FR1 - Scope enforcement
The system must evaluate every request against its defined capabilities
before acting, and must refuse requests that are out of scope or that
attempt prompt injection. A refusal must state what the system CAN help
with instead of just declining silently.

### FR2 - Capability routing
The system must interpret the user's goal and route to the correct
capability node(s). Requests that require information from more than one
capability (e.g. combining documented requirements with actual
implementation state) must invoke all relevant capabilities in the same
turn, not just the first one that seems to match.

### FR3 - Grounded knowledge answers
Answers to questions about the project must be grounded in retrieved
documentation chunks, with source citations. If the retrieved context does
not contain the answer, the system must say so rather than fabricating a
plausible-sounding response.

### FR4 - Repository intelligence
The system must report accurate, current data from the connected GitHub
repository: open issue count, days since last commit, and any
blocker/bug/critical-labeled issues. The engineering health score must be
computed deterministically and be reproducible from the same input data.
This capability may also read one specific source file under `app/` or
`frontend/` when given the exact repo-relative path, so code can be
checked against documentation. It must not perform full-text codebase
search or guess likely paths when the exact path is unknown; it must ask
for the exact path instead.

### FR5 - Artifact generation
On request, the system must generate engineering artifacts (README
sections, Mermaid diagrams) using real context gathered from the other
capabilities in that turn, not generated without any grounding.

### FR6 - Conversation memory
The system must retain recent conversation history within a session so
follow-up questions can reference earlier turns. Conversation history and
the last-generated artifact must persist in SQLite across backend restarts
or crashes, while the rest of the per-request agent state is rebuilt
fresh each turn.

## Non-functional requirements

### NFR1 - Free-tier operation
All external services used must have a free tier sufficient for
development and demo use: GitHub REST API (free, 5,000 req/hr with a
personal token), local embeddings (no API cost), and Claude API calls
(only paid component, billed per call).

### NFR2 - Explainability
Every request must produce an inspectable trace showing which nodes ran
and what each one decided, so the reasoning path is never a black box.

### NFR3 - Graceful degradation
If a capability's required configuration is missing (e.g. no GitHub repo
configured) or an external API call fails, that capability must report the
failure clearly rather than crashing the whole request.

## Out of scope (explicitly, v1)

- Calendar integration / meeting scheduling
- Creating, editing, or closing GitHub issues or pull requests
- Sending notifications, emails, or Slack messages
- Executing arbitrary code on behalf of the user
- Multi-agent collaboration or handoff between separate agents
- Writing to any repository path outside the `generated/` folder
- Full-text search across the codebase or reading files outside allowed source paths

These are documented as future work, not omissions.

### FR7 - Clarification over guessing
When a query is genuinely too ambiguous to route confidently, the system
must ask a specific clarifying question rather than guessing a capability
and risking a fabricated answer. This must not trigger for queries that
are merely broad but answerable.

For source-file reads, the same rule applies when intent is clear but the
exact path is missing: the system must ask for the exact repo-relative
path rather than guessing likely paths or answering from memory about what
the file probably contains.

### FR8 - Explicit-only write actions
The system must never write a local file or commit to GitHub as a side
effect of a query that only asked to preview or generate content. A write
action (save or commit) must only occur when the user's request explicitly
asks for it.

### FR9 - Next-task recommendation
For status/progress/priority queries, the system must recommend a specific
next task grounded in real gathered issue/commit data, weighting unassigned
blocker-labeled issues above routine backlog items. Must not fabricate a
recommendation when there isn't enough data to support one.

### FR10 - Requirement traceability matrix
On request, the system must generate a traceability matrix cross-referencing
actual requirement statements from `requirements.md` against real GitHub
evidence (issue numbers, commits) - never rows derived from GitHub issue
titles alone, since issues are evidence, not requirements.

## Evaluation requirements

The system must be evaluated against a golden dataset of at least 20
queries spanning four categories: happy path, ambiguous, edge case, and
adversarial. Each query must be scored by an LLM-as-judge along the
specific eval dimension it targets:

- **Routing** - did the system invoke the correct capability or
  capabilities for the query?
- **Faithfulness** - is the answer grounded in retrieved/analyzed data,
  with no invented facts?
- **Safety** - did the system correctly refuse out-of-scope or adversarial
  requests?
- **Clarification** - did the system ask for missing information instead
  of guessing, when the query was too ambiguous to route confidently?

Results must be reported both overall and broken down by dimension, so
specific weaknesses (not just an aggregate score) are visible.
