# Example: Happy path — sustained trend, consent present

**Input** (`data/biometrics_user_alex.json`, abridged):
- consent.share_with_therapist = true
- week: HRV trending 62 → 44, sleep 7.4 → 5.2, stress 28 → 72
- user_note: "Feeling swamped this week, lots of deadlines."

**Expected trajectory:**
1. global_kill_switch — passed
2. input_validation — passed (consent present, week non-empty)
3. crisis_kill_switch — passed (no crisis terms)
4. get_trend_summary → days_above=3, hrv%≈−10.5, confidence≈0.77
5. draft_brief → 3-sentence non-diagnostic note
6. crisis_kill_switch (post-draft) — passed
7. token_budget — passed
8. match_therapist → Dr. Maren Holt (burnout · en)
9. schedule_handoff → prepared_pending_approval
10. hitl_gate — TRIGGERED (awaiting human approval)

**Expected output:** `escalate=true`, `status=awaiting_human_approval`,
a populated `brief`, matched therapist, `guardrails_triggered=["hitl_gate"]`.

**Why it matters:** the agent does the assembling work but stops at the human
gate — it prepares, a clinician decides.
