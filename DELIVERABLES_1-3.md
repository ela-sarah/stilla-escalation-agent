# Stilla — Build Deliverables 1–3

**Team:** Anupama Ajith, Modhura Das, Sarah Ela George, Jesslin Ann Mamen, Navneeth Rajesh
**Course:** AI for Marketing & Innovation · Class 6 · ESSEC / École Centrale
**Repository:** https://github.com/ela-sarah/stilla-escalation-agent
**Product UI (Class 4–5 continuity):** https://github.com/navneethrajesh08/stilla-proactive-burnout-monitor

---

## Deliverable 1 — Agentic workflow

**Decision sequence.** When a consented user's stress signals stay above their
personal threshold for three or more days and no crisis indicator is present,
the agent reads the biometric trend, drafts a non-diagnostic therapist hand-off
brief, safety-screens it, matches a clinician, and prepares the hand-off for
human approval — producing a structured decision the Care tab can render.

**Why an agent, not a workflow.** Most of Stilla's product is a workflow (the
daily score, the timed micro-interventions) and we keep it that way on purpose.
This one step is the exception: the supervisor makes a runtime judgement on
whether a given trend shape warrants escalation, weighs a confidence score, and
branches to a crisis-first path when the safety screen fires. Those branches
depend on the data at runtime and cannot be fully hardcoded across the variety
of real trend shapes, which is what justifies the agentic cost here and only
here.

**Anthropic pattern.** Orchestrator–workers — a supervisor loop that decides,
delegating each concrete task (trend summary, brief drafting, therapist match,
hand-off preparation) to a single-purpose worker.

**Success metric.** Two quantitative targets, both measured by the test suite:
escalation precision (a simulated human reviewer judges the drafted brief
relevant) and a hard safety invariant — **zero** crisis-flagged inputs ever
routed to a routine hand-off. The latter is verified directly in
`tests/test_robustness.py` and `tests/test_explainability.py`.

It satisfies the brief's four selection criteria: **high frequency** (an
escalation check runs roughly weekly per active user), **bounded decision space**
(a finite tool set and a small set of terminal statuses), **measurable success**
(the two metrics above), and **recoverable failure** (the agent only ever
*prepares* a hand-off — a human approves before anything is shared, so a wrong
draft is caught and reversible).

---

## Deliverable 2 — Architecture

**Architecture chosen:** Supervisor / Hierarchical.

A single supervisor (`agent/orchestrator.py`) drives the control loop and
enforces a guardrail at each step; single-purpose workers (`agent/tools.py`) do
the concrete work and stay deliberately "dumb" so each is independently testable.

```
                          ┌──────────────────────────────┐
   real input             │       SUPERVISOR (loop)       │
  (biometric  ──────────► │     agent/orchestrator.py     │
   record JSON)           │  claude-sonnet-4-6 (judgement)│
                          └───────────┬──────────────────┘
                                      │  enforces a guardrail at each step
        ┌─────────────────────────────┼──────────────────────────────┐
        ▼                ▼             ▼              ▼                ▼
  global_kill      input_validation  crisis_      token_budget    hitl_gate
   switch          (+consent, PII)   kill_switch  (50k cap)       (human approves)
        │                                                          ▲
        ▼   WORKERS (single-purpose tools)                         │
  ┌──────────────┐ ┌────────────┐ ┌───────────────┐ ┌────────────────────┐
  │get_trend_    │ │draft_brief │ │match_therapist│ │schedule_handoff    │
  │summary       │ │(haiku-4-5) │ │               │ │(simulated MCP)     │
  │(reads file)  │ │            │ │(reads roster) │ │prepared_pending    │
  └──────┬───────┘ └─────┬──────┘ └───────┬───────┘ └─────────┬──────────┘
         └───────────────┴────────────────┴──────────────────┘
                                      │
                                      ▼
                    structured HandoffDecision ──► /traces/<run>.jsonl
                    (aiBrief-compatible)            (audit evidence)
```

**Justification (2 lines).** A health hand-off is a regulated, decomposable,
multi-stage task where each stage must be auditable and gated — exactly the
profile the supervisor/hierarchical model is best for, and the brief's noted
2026 default for capstone projects.

**Trade-off accepted.** The supervisor is a coordination bottleneck and adds
loop overhead versus a flat single-agent ReAct design. We accept that cost in
exchange for auditability and clean human-in-the-loop gating, which the use case
demands.

---

## Deliverable 3 — Tool & MCP stack

**Framework.** Plain Python orchestrator, no heavyweight agent framework. Chosen
for reproducibility and clean separation of concerns over framework polish — the
brief explicitly does not reward technical sophistication, and a no-dependency
core is what lets a reviewer clone and run in under ten minutes with no secrets.
Declared in `requirements.txt` (only optional dependency: `anthropic`).

**Models.** Named in `agent/llm.py`:

| Role | Model | Why |
|---|---|---|
| Supervisor (judgement / orchestration) | `claude-sonnet-4-6` | Best cost/quality for orchestration per the 2026 toolbox |
| Worker (brief drafting, high volume) | `claude-haiku-4-5` | Cheap, fast, sufficient for a templated non-diagnostic note |
| Offline fallback | deterministic stub | Runs the full agent + tests with no API key, for reproducibility |

**MCP / tools.** Four tools, ≥ 4 calls per run:

| Tool | Type | Reads / does | Permissions & scope |
|---|---|---|---|
| `get_trend_summary` | external file read | computes the trend from a biometric record | read-only on the user's consented record |
| `draft_brief` | model worker call | drafts the 3-sentence hand-off note | no training on user data; derived signals only |
| `match_therapist` | external file read | picks a clinician by specialty + language | read-only on the therapist roster |
| `schedule_handoff` | simulated scheduling MCP | **prepares** (never sends) the hand-off | draft-and-suggest only; sending is HITL-gated |

In production, `schedule_handoff` becomes a real scheduling MCP server (e.g.
FastMCP wrapping the booking API) with a hard "draft only" scope; for this build
it is simulated so the repo runs offline. The scheduling tool never auto-sends —
the HITL gate blocks it by design.

---

### Coherence with Classes 4–5

This is the same escalation step our Class 5 product specification named as
Stilla's single true agent (the others are workflows), and the structured output
is shaped to match the `aiBrief` object already rendered by the Class 4–5 product
UI. The agent is the missing action+escalation layer our market analysis
identified as the white space rivals (Oura, Calm, Welltory) leave empty.
