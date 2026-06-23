"""Structured audit logging.

Every tool call, model call, decision, and guardrail trigger is written as one
JSON object per line (JSONL) to traces/<run_id>.jsonl. This is the evidence a
reviewer reads after the fact (explainability) and the source of the audit-log
line shown in the demo.
"""
from __future__ import annotations

import json
import os
import time
import uuid
from datetime import datetime, timezone


class AuditLog:
    def __init__(self, trace_dir: str = "traces", run_id: str | None = None):
        self.run_id = run_id or f"run-{datetime.now(timezone.utc):%Y%m%dT%H%M%S}-{uuid.uuid4().hex[:6]}"
        os.makedirs(trace_dir, exist_ok=True)
        self.path = os.path.join(trace_dir, f"{self.run_id}.jsonl")
        self._lines: list[dict] = []

    def log(self, event: str, **fields):
        record = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "run_id": self.run_id,
            "event": event,
            **fields,
        }
        self._lines.append(record)
        with open(self.path, "a") as f:
            f.write(json.dumps(record) + "\n")
        return record

    def tool_call(self, name: str, args: dict, result_summary: str, ms: float):
        return self.log("tool_call", tool=name, args=args,
                        result=result_summary, latency_ms=round(ms, 1))

    def guardrail(self, name: str, triggered: bool, detail: str):
        return self.log("guardrail", guardrail=name, triggered=triggered, detail=detail)

    def decision(self, status: str, escalate: bool, confidence: float, reasoning: str):
        return self.log("decision", status=status, escalate=escalate,
                        confidence=confidence, reasoning=reasoning)

    @property
    def records(self) -> list[dict]:
        return list(self._lines)


class _Timer:
    def __enter__(self):
        self.t0 = time.perf_counter()
        return self

    def __exit__(self, *exc):
        self.ms = (time.perf_counter() - self.t0) * 1000


def timer() -> _Timer:
    return _Timer()
