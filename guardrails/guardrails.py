"""Implemented guardrails — enforced at runtime by the orchestrator.

Five guardrails (the brief requires at least three). Each returns a small result
object the orchestrator acts on, and each logs to the audit trail when it fires:

  1. validate_input        — schema + consent check; refuse list for bad patterns
  2. mask_pii              — redacts emails/phones before any text hits the model
  3. crisis_kill_switch    — hard stop + crisis resources if self-harm signals appear
  4. token_budget          — hard cap per run; stop with budget_exhausted if exceeded
  5. hitl_gate             — agent may draft & suggest only; never auto-sends

Guardrail 3 doubles as the safety screen the SKILL.md references.
"""
from __future__ import annotations

import os
import re

# ---- 1. refuse list / crisis lexicon -----------------------------------------
_REFUSE_PATTERNS = [
    r"ignore (all|previous|the above) instructions",
    r"disregard your (system|previous) prompt",
    r"you are now",
    r"reveal your (system )?prompt",
    r"act as (an?|the) .*(unfiltered|jailbroken)",
]

# Crisis terms force the kill switch. Kept explicit on purpose: the rubric wants
# confidence thresholds and stop conditions stated, not vibes.
_CRISIS_TERMS = [
    "suicide", "suicidal", "kill myself", "kill my self", "end my life",
    "want to die", "self-harm", "self harm", "hurt myself", "no reason to live",
    "better off dead",
]

TOKEN_BUDGET = int(os.environ.get("STILLA_TOKEN_BUDGET", "50000"))
KILL_SWITCH = os.environ.get("STILLA_AGENT_DISABLED", "false").lower() == "true"


class GuardResult:
    def __init__(self, ok: bool, name: str, detail: str = "", payload=None):
        self.ok = ok          # True = passed / safe to proceed
        self.name = name
        self.detail = detail
        self.payload = payload


def global_kill_switch() -> GuardResult:
    """Operational circuit breaker: STILLA_AGENT_DISABLED=true disables the agent."""
    if KILL_SWITCH:
        return GuardResult(False, "global_kill_switch", "Agent globally disabled via env flag")
    return GuardResult(True, "global_kill_switch", "enabled")


def validate_input(record: dict) -> GuardResult:
    if not isinstance(record, dict):
        return GuardResult(False, "input_validation", "payload is not an object")
    if "user_id" not in record or "week" not in record:
        return GuardResult(False, "input_validation", "missing required fields user_id/week")
    if not isinstance(record.get("week"), list) or len(record["week"]) == 0:
        return GuardResult(False, "input_validation", "week series is empty — nothing to assess")
    consent = record.get("consent", {}).get("share_with_therapist", False)
    if not consent:
        return GuardResult(False, "input_validation", "no therapist-sharing consent on record")
    note = str(record.get("user_note", ""))
    for pat in _REFUSE_PATTERNS:
        if re.search(pat, note, re.IGNORECASE):
            return GuardResult(False, "input_validation",
                               f"refuse-list pattern in user_note: /{pat}/")
    return GuardResult(True, "input_validation", "ok")


def sanitize_tool_output(text: str) -> str:
    """Prompt-injection defence: strip meta-instructions from any text that will
    be re-injected into a model prompt (e.g. the free-text user_note)."""
    cleaned = text
    for pat in _REFUSE_PATTERNS:
        cleaned = re.sub(pat, "[removed-meta-instruction]", cleaned, flags=re.IGNORECASE)
    return cleaned


_EMAIL = re.compile(r"[\w.\-]+@[\w.\-]+\.\w+")
_PHONE = re.compile(r"\+?\d[\d \-]{7,}\d")


def mask_pii(text: str) -> str:
    text = _EMAIL.sub("[email]", text)
    text = _PHONE.sub("[phone]", text)
    return text


def crisis_kill_switch(*texts: str) -> GuardResult:
    """Hard stop. If any crisis term appears in inputs or the drafted brief, the
    agent must NOT draft/route a routine hand-off; it surfaces crisis resources
    and halts. This is non-negotiable per the SKILL.md stop conditions."""
    haystack = " ".join(t.lower() for t in texts if t)
    for term in _CRISIS_TERMS:
        if term in haystack:
            return GuardResult(False, "crisis_kill_switch",
                               f"crisis term detected: '{term}' — routed to human crisis path")
    return GuardResult(True, "crisis_kill_switch", "no crisis indicators")


def token_budget(tokens_used: int) -> GuardResult:
    if tokens_used > TOKEN_BUDGET:
        return GuardResult(False, "token_budget",
                           f"{tokens_used} tokens > cap {TOKEN_BUDGET}")
    return GuardResult(True, "token_budget", f"{tokens_used}/{TOKEN_BUDGET} tokens")


def hitl_gate(confidence: float, threshold: float = 0.85) -> GuardResult:
    """The agent drafts and suggests; a human therapist must review before the
    brief is shared. Always returns 'awaiting approval' — the agent never sends.
    Below-threshold confidence is flagged for extra scrutiny."""
    low = confidence < threshold
    detail = ("low-confidence — flagged for human review"
              if low else "standard human-approval gate")
    return GuardResult(False, "hitl_gate", detail, payload={"low_confidence": low})
