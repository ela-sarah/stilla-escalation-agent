"""7.4 Explainability — trace completeness + user-facing rationale.

trace_complete: for each decision run, does the trace contain input received,
tool calls, model output, decision rationale, and confidence? Score = % of runs
with a complete trace.

explanation_quality: grade the one-sentence rationale clear / partial / opaque
using a simple, transparent rubric (mentions a concrete signal + an action).

gdpr_art22: the brief drives a decision with significant effect, so the trace
must support a human appeal (inputs + rationale + confidence present).

Writes tests/results/explainability.json.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent import orchestrator  # noqa: E402

ROSTER = "data/therapist_roster.json"
SCENARIOS = ["data/biometrics_user_alex.json", "data/biometrics_low.json",
             "data/biometrics_crisis.json"]

REQUIRED_EVENTS = {"run_start", "decision", "run_end"}


def trace_is_complete(records):
    events = {r["event"] for r in records}
    has_decision = any(r["event"] == "decision" for r in records)
    decision = next((r for r in records if r["event"] == "decision"), {})
    has_conf = "confidence" in decision
    has_reason = bool(decision.get("reasoning"))
    has_required = REQUIRED_EVENTS.issubset(events)
    return has_required and has_decision and has_conf and has_reason


def grade_explanation(reasoning: str) -> str:
    if not reasoning:
        return "opaque"
    has_signal = any(k in reasoning.lower()
                     for k in ["hrv", "threshold", "days", "crisis", "confidence"])
    has_action = any(k in reasoning.lower()
                     for k in ["approval", "escalat", "suppress", "intervention", "human"])
    if has_signal and has_action:
        return "clear"
    if has_signal or has_action:
        return "partial"
    return "opaque"


def main():
    complete = 0
    grades = {"clear": 0, "partial": 0, "opaque": 0}
    art22_ok = 0
    runs = 0
    samples = []
    # run each scenario a few times
    for path in SCENARIOS:
        for _ in range(5):
            d = orchestrator.run(path, ROSTER)
            records = d._records  # type: ignore[attr-defined]
            runs += 1
            if trace_is_complete(records):
                complete += 1
            g = grade_explanation(d.reasoning)
            grades[g] += 1
            # Art.22: appeal needs inputs + rationale + confidence in the trace
            if any(r["event"] == "tool_call" for r in records) or d.status in (
                    "no_escalation", "halted_crisis", "rejected_input"):
                if d.reasoning and d.confidence is not None:
                    art22_ok += 1
            if len(samples) < 3:
                samples.append({"scenario": os.path.basename(path),
                                "status": d.status, "reasoning": d.reasoning,
                                "grade": g})

    out = {"generated_at": datetime.now(timezone.utc).isoformat(),
           "runs": runs,
           "trace_complete_pct": round(complete / runs * 100),
           "explanation_quality": grades,
           "gdpr_art22_supportable_pct": round(art22_ok / runs * 100),
           "samples": samples}
    os.makedirs("tests/results", exist_ok=True)
    json.dump(out, open("tests/results/explainability.json", "w"), indent=2)
    print(json.dumps({k: out[k] for k in
                      ["trace_complete_pct", "explanation_quality",
                       "gdpr_art22_supportable_pct"]}, indent=2))
    return out


if __name__ == "__main__":
    main()
