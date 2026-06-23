"""Typed structures the agent consumes and produces.

Kept as plain dataclasses (no pydantic dependency) so the repo installs and
runs with only `anthropic` as an optional extra. The TrendSummary feeds the
draft step; HandoffDecision is the agent's final structured output and matches
the `aiBrief` shape rendered by the Stilla Care tab (src/lib/mock-data.ts).
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any


@dataclass
class TrendSummary:
    user_id: str
    days_above_threshold: int
    hrv_change_pct: float          # negative = decline from baseline
    avg_sleep_h: float
    baseline_sleep_h: float
    avg_stress_5d: float
    intervention_rate_pct: int
    crisis_indicator: bool
    confidence: float              # 0-1, model confidence the pattern is real

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class HandoffDecision:
    """The agent's final structured output."""
    escalate: bool
    status: str                    # e.g. awaiting_human_approval | halted_crisis | no_escalation | budget_exhausted
    confidence: float
    reasoning: str                 # one-sentence rationale (explainability surface)
    brief: dict[str, Any] | None = None      # the aiBrief object, when escalating
    matched_therapist: dict[str, Any] | None = None
    guardrails_triggered: list[str] = field(default_factory=list)
    tokens_used: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
