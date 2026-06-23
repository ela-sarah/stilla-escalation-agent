"""Escalation agent — supervisor / orchestrator-workers control loop.

Decision sequence:
  When a user's stress signals stay above their personal threshold for >= 3 days,
  no crisis indicator is present, and consent exists, the agent assembles a
  structured therapist hand-off brief, runs a safety screen, matches a clinician,
  and prepares the hand-off for HUMAN APPROVAL (it never auto-sends).

Why an agent, not a workflow: the supervisor makes a runtime judgement call on
whether the trend warrants escalation, weighs a confidence score, and branches
to a crisis path when the safety screen fires — branches that cannot be fully
hardcoded across varied trend shapes.
"""
from __future__ import annotations

import json

from agent import llm, tools
from agent.audit import AuditLog, timer
from agent.schemas import HandoffDecision
from guardrails import guardrails as G

ESCALATION_MIN_DAYS = 3
CONFIDENCE_THRESHOLD = 0.85


def run(biometrics_path: str, roster_path: str, lang: str = "en",
        trace_dir: str = "traces") -> HandoffDecision:
    audit = AuditLog(trace_dir=trace_dir)
    audit.log("run_start", biometrics=biometrics_path, mode=llm.runtime_mode(),
              supervisor=llm.SUPERVISOR_MODEL, worker=llm.WORKER_MODEL)

    triggered: list[str] = []
    tokens = 0

    # GUARDRAIL: global kill switch / circuit breaker
    ks = G.global_kill_switch()
    audit.guardrail(ks.name, not ks.ok, ks.detail)
    if not ks.ok:
        triggered.append(ks.name)
        return _finish(audit, HandoffDecision(
            escalate=False, status="halted_kill_switch", confidence=0.0,
            reasoning="Agent globally disabled by operator.", guardrails_triggered=triggered))

    # Load raw record for validation (read happens again inside the tool, by design:
    # the tool is the single source of truth for the computed trend).
    try:
        with open(biometrics_path) as f:
            raw = json.load(f)
    except Exception as e:
        audit.log("error", where="load_input", detail=str(e))
        return _finish(audit, HandoffDecision(
            escalate=False, status="error_bad_input", confidence=0.0,
            reasoning=f"Could not read input: {e}", guardrails_triggered=triggered))

    # GUARDRAIL: input validation + consent + refuse list
    v = G.validate_input(raw)
    audit.guardrail(v.name, not v.ok, v.detail)
    if not v.ok:
        triggered.append(v.name)
        return _finish(audit, HandoffDecision(
            escalate=False, status="rejected_input", confidence=0.0,
            reasoning=f"Input rejected: {v.detail}", guardrails_triggered=triggered))

    user_note = G.sanitize_tool_output(G.mask_pii(str(raw.get("user_note", ""))))

    # GUARDRAIL: crisis kill switch on the inbound signal (before any drafting)
    c_in = G.crisis_kill_switch(user_note)
    audit.guardrail(c_in.name, not c_in.ok, c_in.detail)
    if not c_in.ok:
        triggered.append(c_in.name)
        audit.decision("halted_crisis", False, 1.0, c_in.detail)
        return _finish(audit, HandoffDecision(
            escalate=False, status="halted_crisis", confidence=1.0,
            reasoning="Crisis indicator detected — routed to human crisis resources, "
                      "routine hand-off suppressed.",
            guardrails_triggered=triggered))

    # TOOL 1: trend summary (external source)
    with timer() as t:
        summary, rec = tools.get_trend_summary(biometrics_path)
    audit.tool_call("get_trend_summary", {"path": biometrics_path},
                    f"days_above={summary.days_above_threshold} hrv%={summary.hrv_change_pct} "
                    f"conf={summary.confidence}", t.ms)

    # SUPERVISOR JUDGEMENT: does the trend warrant escalation?
    if summary.days_above_threshold < ESCALATION_MIN_DAYS:
        audit.decision("no_escalation", False, summary.confidence,
                       "Trend below escalation threshold.")
        return _finish(audit, HandoffDecision(
            escalate=False, status="no_escalation", confidence=summary.confidence,
            reasoning=f"Only {summary.days_above_threshold} days above threshold "
                      f"(need >= {ESCALATION_MIN_DAYS}); continue gentle interventions.",
            guardrails_triggered=triggered))

    patient = str(rec.get("user_id", "user")).capitalize()

    # TOOL 2: draft the brief (worker model)
    with timer() as t:
        brief, used = tools.draft_brief(summary, patient)
    tokens += used
    audit.tool_call("draft_brief", {"model": llm.WORKER_MODEL},
                    f"{len(brief['narrative_text'])} chars, {used} tokens", t.ms)

    # GUARDRAIL: crisis screen on the DRAFTED text too (defence in depth)
    c_out = G.crisis_kill_switch(brief["narrative_text"])
    audit.guardrail(c_out.name + "_postdraft", not c_out.ok, c_out.detail)
    if not c_out.ok:
        triggered.append("crisis_kill_switch")
        return _finish(audit, HandoffDecision(
            escalate=False, status="halted_crisis", confidence=1.0,
            reasoning="Crisis language surfaced in draft — suppressed and escalated to human.",
            guardrails_triggered=triggered, tokens_used=tokens))

    # GUARDRAIL: token budget
    tb = G.token_budget(tokens)
    audit.guardrail(tb.name, not tb.ok, tb.detail)
    if not tb.ok:
        triggered.append(tb.name)
        return _finish(audit, HandoffDecision(
            escalate=False, status="budget_exhausted", confidence=summary.confidence,
            reasoning=tb.detail, guardrails_triggered=triggered, tokens_used=tokens))

    # TOOL 3: match a therapist (external source)
    with timer() as t:
        therapist = tools.match_therapist(roster_path, lang=lang)
    audit.tool_call("match_therapist", {"lang": lang}, therapist["name"], t.ms)

    # TOOL 4: prepare the hand-off (simulated scheduling MCP)
    with timer() as t:
        sched = tools.schedule_handoff(therapist, brief)
    audit.tool_call("schedule_handoff", {"therapist_id": therapist["id"]},
                    sched["status"], t.ms)

    # GUARDRAIL: HITL approval gate — agent prepares, human sends.
    gate = G.hitl_gate(summary.confidence, CONFIDENCE_THRESHOLD)
    triggered.append(gate.name)
    audit.guardrail(gate.name, True, gate.detail)

    reasoning = (
        f"{summary.days_above_threshold} days above threshold with HRV "
        f"{summary.hrv_change_pct}% vs baseline (confidence {summary.confidence}); "
        f"brief drafted and matched to {therapist['name']}, awaiting human approval."
    )
    audit.decision("awaiting_human_approval", True, summary.confidence, reasoning)

    return _finish(audit, HandoffDecision(
        escalate=True, status="awaiting_human_approval", confidence=summary.confidence,
        reasoning=reasoning, brief=brief, matched_therapist=therapist,
        guardrails_triggered=triggered, tokens_used=tokens))


def _finish(audit: AuditLog, decision: HandoffDecision) -> HandoffDecision:
    audit.log("run_end", status=decision.status, escalate=decision.escalate,
              tokens=decision.tokens_used, trace=audit.path)
    decision._trace_path = audit.path  # type: ignore[attr-defined]
    decision._records = audit.records  # type: ignore[attr-defined]
    return decision
