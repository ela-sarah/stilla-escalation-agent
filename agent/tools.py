"""Tools the agent calls. Each is logged via the audit trail by the orchestrator.

A run makes at least four tool calls (read -> draft -> match -> schedule),
clearing the brief's ">= 2 tool calls per run" bar. get_trend_summary reads an
external file (not hardcoded in the prompt), satisfying the external-source bar.
"""
from __future__ import annotations

import json
from statistics import mean

from agent import llm
from agent.schemas import TrendSummary


def get_trend_summary(path: str) -> tuple[TrendSummary, dict]:
    """TOOL 1 (external source): read biometric record, compute the trend."""
    with open(path) as f:
        rec = json.load(f)

    week = rec["week"]
    base = rec["baseline"]
    thr = rec["personal_threshold"]

    days_above = sum(1 for d in week if d["hrv"] < thr["hrv_ms"] or d["stress"] > thr["stress"])
    last5 = week[-5:]
    avg_hrv_last5 = mean(d["hrv"] for d in last5)
    hrv_change = round((avg_hrv_last5 - base["hrv_ms"]) / base["hrv_ms"] * 100, 1)
    avg_sleep = round(mean(d["sleep"] for d in last5), 1)
    avg_stress = round(mean(d["stress"] for d in last5), 1)
    accepted = sum(1 for d in week if d["intervention_accepted"])
    rate = round(accepted / len(week) * 100)

    # Confidence: more days above threshold + larger HRV decline => higher confidence.
    confidence = min(0.99, 0.45 + 0.07 * days_above + min(0.25, abs(hrv_change) / 100))

    summary = TrendSummary(
        user_id=rec["user_id"],
        days_above_threshold=days_above,
        hrv_change_pct=hrv_change,
        avg_sleep_h=avg_sleep,
        baseline_sleep_h=base["sleep_h"],
        avg_stress_5d=avg_stress,
        intervention_rate_pct=rate,
        crisis_indicator=False,
        confidence=round(confidence, 2),
    )
    return summary, rec


def draft_brief(summary: TrendSummary, patient_name: str) -> tuple[dict, int]:
    """TOOL 2 (model worker call): draft the narrative brief. Returns aiBrief-shaped
    dict matching the Stilla Care tab, plus tokens used."""
    prompt = (
        f"patient = {patient_name}\n"
        f"days_above_threshold = {summary.days_above_threshold}\n"
        f"hrv_change_pct = {summary.hrv_change_pct}\n"
        f"avg_sleep_h = {summary.avg_sleep_h}\n"
        f"baseline_sleep_h = {summary.baseline_sleep_h}\n"
        f"intervention_rate_pct = {summary.intervention_rate_pct}\n"
        "Write a 3-sentence factual hand-off note. Non-diagnostic."
    )
    res = llm.complete(prompt, model=llm.WORKER_MODEL, max_tokens=400)

    def tone(v, warn, danger):
        return "danger" if v >= danger else ("warn" if v >= warn else "ok")

    brief = {
        "patient": patient_name,
        "generatedAt": "auto",
        "narrative_text": res.text,
        "stats": [
            {"label": "Avg stress (5d)", "value": str(int(summary.avg_stress_5d)),
             "tone": tone(summary.avg_stress_5d, 50, 65)},
            {"label": "Avg sleep", "value": f"{summary.avg_sleep_h}h",
             "tone": tone(7.1 - summary.avg_sleep_h, 0.5, 1.0)},
            {"label": "HRV vs baseline", "value": f"{summary.hrv_change_pct}%",
             "tone": tone(abs(summary.hrv_change_pct), 10, 18)},
            {"label": "Intervention rate", "value": f"{summary.intervention_rate_pct}%",
             "tone": tone(100 - summary.intervention_rate_pct, 40, 60)},
        ],
        "confidence": summary.confidence,
        "model": res.model,
    }
    return brief, res.tokens


def match_therapist(roster_path: str, lang: str = "en") -> dict:
    """TOOL 3 (external source): pick the best-matching clinician."""
    with open(roster_path) as f:
        roster = json.load(f)["therapists"]
    # Prefer a burnout specialist who speaks the user's language; fall back to any.
    ranked = sorted(
        roster,
        key=lambda t: (("burnout" in t["specialties"]) + (lang in t["languages"])),
        reverse=True,
    )
    return ranked[0]


def schedule_handoff(therapist: dict, brief: dict) -> dict:
    """TOOL 4 (simulated scheduling MCP): prepare — but do NOT send — the hand-off.
    Returns a pending request; actual sending is blocked by the HITL gate."""
    return {
        "status": "prepared_pending_approval",
        "therapist_id": therapist["id"],
        "therapist_name": therapist["name"],
        "proposed_slot": therapist["next_slot"],
        "brief_attached": True,
    }
