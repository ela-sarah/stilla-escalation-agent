"""Model client.

Two model roles, named per the Class 6 toolbox:
  - SUPERVISOR_MODEL = claude-sonnet-4-6   (orchestration / judgement)
  - WORKER_MODEL     = claude-haiku-4-5     (high-volume drafting)

If ANTHROPIC_API_KEY is set and the `anthropic` package is installed, real API
calls are made. Otherwise the client falls back to a deterministic, offline
"mock" that produces a structured draft from the numeric inputs. The fallback
exists so a reviewer can clone and run the agent — and the full test suite —
in under 10 minutes with no secrets. Token usage is counted in both modes so
the carbon test produces real numbers.
"""
from __future__ import annotations

import os
import re

SUPERVISOR_MODEL = "claude-sonnet-4-6"
WORKER_MODEL = "claude-haiku-4-5"

_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "").strip()
_USE_REAL = bool(_API_KEY)

try:  # optional dependency
    import anthropic  # type: ignore
    _HAVE_SDK = True
except Exception:
    _HAVE_SDK = False


def _approx_tokens(text: str) -> int:
    # ~4 chars/token is the standard rough heuristic; good enough for a carbon estimate.
    return max(1, len(text) // 4)


class LLMResult:
    def __init__(self, text: str, tokens_in: int, tokens_out: int, model: str, mode: str):
        self.text = text
        self.tokens_in = tokens_in
        self.tokens_out = tokens_out
        self.tokens = tokens_in + tokens_out
        self.model = model
        self.mode = mode  # "api" or "mock"


def complete(prompt: str, *, model: str = WORKER_MODEL, system: str = "", max_tokens: int = 600) -> LLMResult:
    """Single completion. Real API when a key is present, else deterministic mock."""
    if _USE_REAL and _HAVE_SDK:
        client = anthropic.Anthropic(api_key=_API_KEY)
        msg = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system or "You are Stilla's clinical hand-off drafter. Calm, factual, never diagnostic.",
            messages=[{"role": "user", "content": prompt}],
        )
        text = "".join(block.text for block in msg.content if getattr(block, "type", "") == "text")
        return LLMResult(text, msg.usage.input_tokens, msg.usage.output_tokens, model, "api")

    # ---- deterministic offline fallback ----
    text = _mock_draft(prompt)
    return LLMResult(text, _approx_tokens(system + prompt), _approx_tokens(text), model, "mock")


def _mock_draft(prompt: str) -> str:
    """Build a templated, grounded narrative from numbers found in the prompt.

    Deterministic: identical input -> identical output, which is what makes the
    bias and explainability tests reproducible.
    """
    def grab(key: str, default: str = "?") -> str:
        m = re.search(rf"{key}\s*=\s*([\-\d\.]+)", prompt)
        return m.group(1) if m else default

    days = grab("days_above_threshold")
    hrv = grab("hrv_change_pct")
    sleep = grab("avg_sleep_h")
    base_sleep = grab("baseline_sleep_h")
    accept = grab("intervention_rate_pct")
    name = "the user"
    m = re.search(r"patient\s*=\s*([A-Za-z]+)", prompt)
    if m:
        name = m.group(1)

    return (
        f"{name} has shown elevated stress for {days} days, driven mainly by higher "
        f"meeting density and reduced sleep (avg {sleep}h vs. usual {base_sleep}h). "
        f"HRV declined {hrv}% from baseline. Intervention acceptance fell to {accept}% this "
        f"week, which may indicate an emotional-avoidance pattern. No crisis indicators "
        f"detected. Recommend exploring workload boundaries and sleep hygiene."
    )


def runtime_mode() -> str:
    return "api" if (_USE_REAL and _HAVE_SDK) else "mock"
