"""7.3 Carbon — energy and CO2 per agent run, with an SLM comparison.

Method:
  tokens/run  -> measured from real runs (token counter in agent.llm)
  kWh/run     -> tokens * energy_per_token (public order-of-magnitude reference)
  gCO2eq/run  -> kWh * grid intensity (France = 60 gCO2eq/kWh)
  monthly     -> gCO2eq/run * runs/month at MAU target

Energy-per-token references (order-of-magnitude, public disclosures / mlco2):
  frontier (Sonnet-class) ~ 3.0e-6 kWh/token
  small/worker (Haiku-class) ~ 1.0e-6 kWh/token
  SLM (on-device / distilled) ~ 0.2e-6 kWh/token

Writes tests/results/carbon.json.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent import orchestrator  # noqa: E402

ROSTER = "data/therapist_roster.json"
GRID_FR = 60          # gCO2eq / kWh (France)
MAU = 50_000          # target monthly active users
RUNS_PER_USER_PER_MONTH = 4  # escalation checks ~weekly

ENERGY_PER_TOKEN_KWH = {
    "frontier_sonnet": 3.0e-6,
    "worker_haiku": 1.0e-6,
    "slm_on_device": 0.2e-6,
}


def measure_tokens_per_run(n=10):
    totals = []
    for _ in range(n):
        d = orchestrator.run("data/biometrics_user_alex.json", ROSTER)
        totals.append(d.tokens_used)
    return round(sum(totals) / len(totals))


def row(model_key, tokens):
    e_tok = ENERGY_PER_TOKEN_KWH[model_key]
    kwh = tokens * e_tok
    g = kwh * GRID_FR
    monthly_runs = MAU * RUNS_PER_USER_PER_MONTH
    monthly_kg = g * monthly_runs / 1000
    return {"model": model_key, "tokens_per_run": tokens,
            "kWh_per_run": round(kwh, 8), "gCO2eq_per_run": round(g, 5),
            "monthly_kgCO2eq_at_MAU": round(monthly_kg, 1)}


def main():
    tokens = measure_tokens_per_run()
    # Current agent uses the worker model for drafting.
    table = [
        row("frontier_sonnet", tokens),   # hypothetical if everything ran on Sonnet
        row("worker_haiku", tokens),      # current configuration
        row("slm_on_device", tokens),     # SLM substitution for the draft step
    ]
    out = {"generated_at": datetime.now(timezone.utc).isoformat(),
           "grid_gCO2eq_per_kWh": GRID_FR, "mau": MAU,
           "runs_per_user_per_month": RUNS_PER_USER_PER_MONTH,
           "measured_tokens_per_run": tokens,
           "table": table,
           "slm_feasibility": ("The draft step is templated and low-variance, so a "
                               "distilled on-device SLM is feasible and cuts per-run CO2 "
                               "~5x vs Haiku and ~15x vs Sonnet, trading a small amount of "
                               "narrative fluency we accept for a non-diagnostic note.")}
    os.makedirs("tests/results", exist_ok=True)
    json.dump(out, open("tests/results/carbon.json", "w"), indent=2)
    print(json.dumps({"tokens_per_run": tokens, "table": table}, indent=2))
    return out


if __name__ == "__main__":
    main()
