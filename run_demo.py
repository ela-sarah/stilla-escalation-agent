"""Demo runner — `python run_demo.py [--scenario happy|crisis|low]`.

Prints the agent trajectory (tool calls + guardrail triggers), one audit-log
line, and the final structured decision. This is the script used for the
recorded backup video: real input on screen -> visible trajectory -> a guardrail
firing -> an audit line -> the brief.
"""
from __future__ import annotations

import argparse
import json

from agent import orchestrator

SCENARIOS = {
    "happy": "data/biometrics_user_alex.json",
    "crisis": "data/biometrics_crisis.json",
    "low": "data/biometrics_low.json",
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenario", choices=SCENARIOS, default="happy")
    ap.add_argument("--lang", default="en")
    args = ap.parse_args()

    path = SCENARIOS[args.scenario]
    print(f"\n=== STILLA ESCALATION AGENT · scenario={args.scenario} · input={path} ===\n")

    decision = orchestrator.run(path, "data/therapist_roster.json", lang=args.lang)

    # Replay the trajectory from the trace
    print("--- AGENT TRAJECTORY ---")
    for r in decision._records:  # type: ignore[attr-defined]
        if r["event"] == "tool_call":
            print(f"  [tool]      {r['tool']:<20} -> {r['result']}  ({r['latency_ms']}ms)")
        elif r["event"] == "guardrail":
            mark = "TRIGGERED" if r["triggered"] else "passed"
            print(f"  [guardrail] {r['guardrail']:<24} {mark}: {r['detail']}")
        elif r["event"] == "decision":
            print(f"  [decision]  {r['status']} (confidence {r['confidence']})")

    # One representative audit-log line (for the demo requirement #5)
    print("\n--- SAMPLE AUDIT LINE ---")
    last_decision = [r for r in decision._records if r["event"] == "decision"]  # type: ignore
    print("  " + json.dumps(last_decision[-1] if last_decision else decision._records[-1]))

    print("\n--- STRUCTURED OUTPUT (aiBrief-compatible) ---")
    out = decision.to_dict()
    print(json.dumps(out, indent=2)[:1400])

    print(f"\nStatus: {decision.status} | escalate={decision.escalate} "
          f"| tokens={decision.tokens_used}")
    print(f"Trace written to: {decision._trace_path}\n")  # type: ignore[attr-defined]


if __name__ == "__main__":
    main()
