# Architecture — Supervisor / Hierarchical (orchestrator–workers)

```
                          ┌─────────────────────────────┐
   real input             │      SUPERVISOR (loop)       │
  (biometric  ──────────► │   agent/orchestrator.py      │
   record JSON)           │  claude-sonnet-4-6 (judgement)│
                          └───────────┬─────────────────┘
                                      │  enforces guardrails at each step
        ┌─────────────────────────────┼──────────────────────────────┐
        ▼                ▼             ▼              ▼                ▼
  global_kill      input_validation  crisis_      token_budget    hitl_gate
   switch          (+consent,PII)    kill_switch  (50k cap)       (human approves)
        │                                                          ▲
        ▼   WORKERS (single-purpose tools, agent/tools.py)         │
  ┌───────────────┐ ┌────────────┐ ┌───────────────┐ ┌───────────────────┐
  │get_trend_     │ │draft_brief │ │match_therapist│ │schedule_handoff   │
  │summary        │ │(haiku-4-5) │ │               │ │(simulated MCP)    │
  │(reads file)   │ │            │ │(reads roster) │ │prepared_pending   │
  └───────┬───────┘ └─────┬──────┘ └───────┬───────┘ └─────────┬─────────┘
          │               │                │                   │
          └───────────────┴────────────────┴───────────────────┘
                                      │
                                      ▼
                         structured HandoffDecision  ──►  /traces/<run>.jsonl
                         (aiBrief-compatible)              (audit evidence)
```

**Why this shape:** the supervisor holds the judgement (escalate or not, crisis
branch, confidence) while workers stay dumb and single-purpose — which keeps each
tool testable and each guardrail enforceable at a known point in the loop.

**Trade-off accepted:** supervisor is a coordination bottleneck and adds loop
overhead vs. a flat single-agent ReAct design; we take that for auditability and
clean HITL gating, which the use case (a health hand-off) demands.
