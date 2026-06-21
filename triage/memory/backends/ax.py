"""Arize AX trace-query backend — STUB. The migration agent implements this.

AX (app.arize.com) is where the Arize sponsor judges, so the trace backend is being
migrated Phoenix -> AX. AX shares the OpenTelemetry/OpenInference foundation with
Phoenix, so the spans are the SAME shape; only the read-back query API differs
(the `ax` CLI / Arize export SDK vs `phoenix.client`).

To wire this up: implement `fetch_prior_run_history` to return the same
`list[PriorAttempt]` contract that `backends/phoenix.py` produces — one row per prior
`repro_attempt`, with `reproduced` taken from the honest `bug.detected` signal and
`fidelity_*` as optional enrichment — then set
`triage.memory.history.TRACE_BACKEND = "ax"`.

Until then this raises NotImplementedError; the seam's caller
(`triage.memory.load_learned_context`) guards every backend call, so even if the AX
backend is selected before it is wired, a run degrades gracefully to the inner loop
rather than crashing.
"""
from __future__ import annotations

from triage.memory.types import PriorAttempt


def fetch_prior_run_history(cfg, *, issue_url: str, limit: int = 5) -> list[PriorAttempt]:
    raise NotImplementedError(
        "Arize AX trace-query backend not yet wired (migration in progress). "
        "Implement this to return the same list[PriorAttempt] contract as "
        "triage/memory/backends/phoenix.py, then set history.TRACE_BACKEND = 'ax'."
    )
