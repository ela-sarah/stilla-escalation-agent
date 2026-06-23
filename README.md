# Stilla — Therapist Hand-off Escalation Agent

The one genuinely agentic workflow in [Stilla](https://github.com/navneethrajesh08/stilla-proactive-burnout-monitor):
when a user's stress signals stay above their personal threshold for several
days — and there is no crisis signal and consent exists — the agent assembles a
clinician-ready hand-off brief, runs a safety screen, matches a therapist, and
**prepares the hand-off for human approval**. It never auto-sends.

Built for Class 6 (Build Your Agent). This repo is the running artefact: agent
code, a SKILL.md, implemented guardrails, four test suites, and run traces.

## Run it in three commands

```bash
git clone <this-repo> && cd stilla-agent
python3 --version            # 3.9+ ; no install needed for the offline demo
python3 run_demo.py --scenario happy
```

Runs with **no API key** via a deterministic offline fallback. For real model
calls: `cp .env.example .env`, add `ANTHROPIC_API_KEY`, `pip install -r requirements.txt`.

Try the other scenarios:

```bash
python3 run_demo.py --scenario crisis   # crisis term -> hard stop, no brief
python3 run_demo.py --scenario low      # healthy week -> no escalation
```

Run the full test suite (regenerates `tests/results/REPORT.md`):

```bash
python3 tests/run_all.py
```

## Workflow & architecture (Deliverables 1–2)

- **Decision sequence.** When a consented user is >= 3 days above their personal
  stress threshold with no crisis signal, the agent drafts a therapist hand-off
  brief, safety-screens it, matches a clinician, and prepares it for human
  approval.
- **Agent, not workflow.** The supervisor makes a runtime judgement on whether
  the trend warrants escalation, weighs a confidence score, and branches to a
  crisis path when the safety screen fires — branches that cannot be hardcoded
  across varied trend shapes.
- **Anthropic pattern:** orchestrator–workers. **Architecture:** Supervisor /
  Hierarchical (a supervisor loop driving single-purpose tool workers).
- **Trade-off accepted:** coordination overhead / a supervisor bottleneck, in
  exchange for auditability and clean human-in-the-loop gating.
- **Success metric:** escalation precision — the matched brief is judged relevant
  by a (simulated) human reviewer; plus 0 crisis inputs ever routed to a routine
  hand-off (tested).

## Tool & MCP stack (Deliverable 3)

- **Framework:** plain Python orchestrator (no heavyweight dependency) — chosen
  for reproducibility and clean separation of concerns over framework polish.
- **Models:** supervisor `claude-sonnet-4-6`, worker `claude-haiku-4-5`
  (named in `agent/llm.py`); deterministic offline fallback when no key is set.
- **Tools:** `get_trend_summary` (reads external biometric file),
  `draft_brief` (worker model), `match_therapist` (reads roster),
  `schedule_handoff` (simulated scheduling MCP). >= 4 tool calls per run.

## Guardrails (Deliverable 6) — five implemented, in `/guardrails/`

| Guardrail | What it does | How to see it fire |
|---|---|---|
| global_kill_switch | `STILLA_AGENT_DISABLED=true` disables the agent | set the env var, run any scenario |
| input_validation | schema + consent + refuse list + empty-week | `--scenario` with no-consent input (tests) |
| crisis_kill_switch | hard stop on self-harm terms, in note **and** draft | `python3 run_demo.py --scenario crisis` |
| token_budget | hard per-run cap, stops with `budget_exhausted` | lower `STILLA_TOKEN_BUDGET` |
| hitl_gate | agent prepares only; human approves before send | every escalating run ends `awaiting_human_approval` |

Plus PII masking and prompt-injection sanitisation on free-text before it
reaches the model.

## Tests (Deliverable 7) — `/tests/`, results in `/tests/results/`

`robustness` · `bias` · `carbon` · `explainability`. Headline numbers live in
[`tests/results/REPORT.md`](tests/results/REPORT.md), regenerated from real runs.
We disclose one honest gap (first-tool failure isn't wrapped yet) rather than
claim 100% everywhere.

## Repo map

```
agent/          orchestrator.py · llm.py · tools.py · schemas.py · audit.py
skills/         escalation/SKILL.md + examples/ (happy path, crisis edge case)
guardrails/     guardrails.py · refuse list
data/           biometric scenarios + therapist roster (external sources)
tests/          four suites + inputs/ + results/REPORT.md
traces/         JSONL run traces (audit evidence for the demo)
run_demo.py     CLI: real input -> trajectory -> guardrail -> audit line -> brief
```

## Connecting to the Stilla UI (later)

The agent's `brief` output is shaped to match `aiBrief` in the frontend's
`src/lib/mock-data.ts`. To wire the Care tab to the live agent, replace the
hardcoded `aiBrief` import with a single POST to an `/escalate` endpoint that
calls `agent.orchestrator.run(...)`. The demo does not require this — the agent
stands alone — but the shapes already line up so the swap is small.
