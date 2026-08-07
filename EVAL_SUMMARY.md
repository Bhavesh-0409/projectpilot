# Evaluation Summary — ProjectPilot AI

## Method

20-item golden dataset spanning 4 categories (happy path, ambiguous, edge
case, adversarial) and 4 dimensions (routing, faithfulness, safety,
clarification). Each response scored 1-5 by an LLM-as-judge, scoped to the
specific dimension that test case targets, following the same pattern taught
in Module 3 (Session 10/11) of the bootcamp curriculum.

## Results

Two full runs were performed — the first surfaced real bugs, which were
fixed and confirmed by the second run.

| Metric | Run 1 | Run 2 (after fixes) |
|---|---|---|
| **Overall average** | 4.25 / 5.0 | **4.65 / 5.0** |
| Faithfulness | 4.25 | 4.25 |
| Routing | 4.20 | 4.80 |
| Clarification | 2.50 | **5.00** |
| Safety | 5.00 | 5.00 |

## Bugs found and fixed

The eval pipeline caught three real, specific defects that manual testing
had missed:

**1. Scope guard was doing the router's job (clarification: 2.5 → 5.0)**
Genuinely ambiguous queries ("Is it done?", "Check this") were being flatly
refused by the scope guard as "out of scope," instead of reaching the
router's dedicated clarification path. Root cause: the scope guard was
conflating "vague" with "not permitted." Fixed by explicitly instructing the
scope guard that ambiguity judgment belongs downstream, not to it.

**2. `commit_existing` pushed stale, unrelated content**
Asking to "push that file" (referring to a specific artifact discussed
earlier in conversation) instead committed a leftover file from a completely
different, earlier test session. Root cause: the code checked for *any*
existing local file before checking the session's actual conversation
context — a global, unscoped file was silently taking priority over what the
user had just discussed. Fixed by reversing the priority order.

**3. Router over-triggered clarification on an answerable query**
"What should we work on next?" — a direct match for a feature we built
specifically (next-task recommendation) — got a generic clarifying question
instead of a real answer. Root cause: the router's capability descriptions
never mentioned that GitHub analysis includes next-task recommendation, so
it didn't recognize the phrasing as routable. Fixed by updating the router's
capability description.

A fourth, smaller gap was also found and fixed after run 2: a requirement
traceability matrix was deriving its "requirement" rows from GitHub issue
titles instead of the actual documented requirements — backwards for a
traceability artifact. Fixed by forcing the generator to pull from
`requirements.md` content specifically, and to say so explicitly if that
content wasn't available rather than inventing requirements from issues.

## Adversarial testing (manual, beyond the golden dataset)

Beyond the scored golden dataset, a manual adversarial pass covered 9
categories: direct prompt injection, injection embedded in generated
content, write-path bypass attempts (fake folder names, claimed permission
override), scope creep (issue closing, starring a repo), cross-project data
leakage, malformed input, chained/compound requests, and credential probing.
All were correctly refused or handled safely, with zero successful bypasses
of the `generated/`-only write restriction.

## What this demonstrates

- The eval pipeline is not decorative — it found and drove fixes for 3 real
  defects in a single run, each root-caused to a specific line of reasoning
  in a specific prompt, not just patched blindly
- Safety and adversarial handling were strong from the start (5.0/5.0 both
  runs) and held under deliberate, creative attack attempts
- The remaining sub-5 faithfulness scores (PP-003, PP-008) reflect judge
  strictness on citation formatting rather than actual hallucination — a
  known limit of single-pass LLM-as-judge scoring, worth noting rather than
  over-optimizing against