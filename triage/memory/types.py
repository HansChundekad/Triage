"""Backend-agnostic contract for prior-run history.

`PriorAttempt` is the type every layer above the trace-query seam speaks. It is
deliberately backend-neutral: the Phoenix and (future) Arize AX read-back adapters
both produce `list[PriorAttempt]`, and `distill_hint` / `load_learned_context`
never see anything backend-specific.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PriorAttempt:
    run_id: str                 # trace/run id this attempt belongs to
    attempt_number: int         # attempt index as recorded (may collide across redirects)
    start_time: str             # honest within-run ordering key (number is unreliable)
    reproduced: bool            # the honest rule-8 reproduction signal for this attempt
    fidelity_label: str         # optional enrichment from an eval annotation ("" if absent)
    fidelity_score: float | None
