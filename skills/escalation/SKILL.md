---
name: therapist-handoff-escalation
description: >
  Decide whether a user's sustained stress signals warrant a human therapist
  hand-off, draft a factual non-diagnostic brief, run a safety screen, match a
  clinician, and prepare the hand-off for human approval. Never auto-sends.
version: 0.1.0
model_hints:
  supervisor: claude-sonnet-4-6
  worker: claude-haiku-4-5
  tested_offline: deterministic fallback (no API key required)
---

# Skill: Therapist Hand-off Escalation

## Goal
Teach the agent to convert a sustained, consented stress pattern into a
clinician-ready hand-off brief — and to know when **not** to (insufficient
trend, no consent, or a crisis signal that requires a different, human-first
path). The agent assists; a human therapist always reviews before anything is
shared. This skill is the one genuinely agentic step in Stilla: it requires a
runtime judgement that cannot be fully hardcoded.

## Inputs
- `biometrics` (JSON): user_id, consent block, baseline, personal_threshold,
  a 7-day `week` series (hrv, sleep, stress, intervention_accepted), history,
  and a free-text `user_note`.
- `roster` (JSON): available therapists with specialties, languages, next slot.

## Outputs (structured)
A `HandoffDecision` object:
```json
{
  "escalate": true,
  "status": "awaiting_human_approval",
  "confidence": 0.86,
  "reasoning": "one sentence, signal + action",
  "brief": { "...aiBrief-compatible..." },
  "matched_therapist": { "...": "..." },
  "guardrails_triggered": ["hitl_gate"],
  "tokens_used": 134
}
```
`status` is one of: `awaiting_human_approval`, `no_escalation`, `halted_crisis`,
`rejected_input`, `budget_exhausted`, `halted_kill_switch`, `error_bad_input`.

## Procedure
1. **Check the global kill switch.** If `STILLA_AGENT_DISABLED=true`, stop with
   `halted_kill_switch`.
2. **Validate input.** Require `user_id`, a non-empty `week`, and
   `consent.share_with_therapist == true`. Scan `user_note` against the refuse
   list. On failure → stop with `rejected_input`.
3. **Mask PII and sanitise** the `user_note` (strip emails/phones and any
   meta-instructions) before it is ever placed in a model prompt.
4. **Crisis screen (inbound).** If any crisis term appears in the note → stop
   with `halted_crisis`, surface crisis resources, and do **not** draft a routine
   brief. This is a hard stop.
5. **Compute the trend** (tool `get_trend_summary`): days above personal
   threshold, HRV % vs baseline, avg sleep, intervention acceptance, confidence.
6. **Judgement — escalate?** If `days_above_threshold < 3`, stop with
   `no_escalation` (continue gentle interventions). Otherwise proceed.
7. **Draft the brief** (worker model, tool `draft_brief`): 3-sentence factual,
   non-diagnostic note in Stilla's calm voice.
8. **Crisis screen (post-draft).** Re-run the screen on the drafted text. Any
   hit → `halted_crisis`.
9. **Token budget.** If cumulative tokens > cap (default 50k) → stop with
   `budget_exhausted`.
10. **Match a clinician** (tool `match_therapist`) by specialty + language.
11. **Prepare the hand-off** (tool `schedule_handoff`) as *pending approval*.
12. **HITL gate.** Always stop at `awaiting_human_approval`. The agent never
    sends. If `confidence < 0.85`, flag the draft for extra human scrutiny.

## Stop conditions (non-negotiable)
- Any crisis term, inbound or in the draft → `halted_crisis`, human-first path.
- No consent / empty week / refuse-list hit → `rejected_input`.
- Token budget exceeded → `budget_exhausted`.
- The agent **never** auto-sends a brief or books a session without human
  approval, regardless of confidence.

## Failure handling
- **Tool returns empty/None:** retry once; if still empty, stop with an
  `error_*` status and a human-readable reason (do not fabricate a brief).
- **Tool raises/times out:** degrade to an `error_*` status, not a crash.
  *(Known gap: a failure of the first tool is not yet wrapped — see
  tests/results/REPORT.md. Scheduled fix.)*
- **Low confidence (<0.85):** still escalate, but mark the draft for closer
  human review rather than presenting it as high-certainty.

## Examples
See `examples/`:
- `happy_path.md` — sustained trend, consent present → brief drafted, awaiting
  approval.
- `crisis_edge_case.md` — crisis term in the note → routine hand-off suppressed,
  crisis path taken.

Tested with three inputs before any demo: happy path, crisis edge case, and an
adversarial prompt-injection note (all in `/tests/`).
