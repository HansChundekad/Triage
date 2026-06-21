"""Backend-agnostic seam for reading prior-run history out of the trace backend.

7.5's learned-context injection depends ONLY on `fetch_prior_run_history` returning
a `list[PriorAttempt]`. The actual trace-query is surface-specific (it differs
between open-source Phoenix and Arize AX), so it lives behind this single function —
swapping backends is one change here, not scattered through the codebase.

MIGRATION NOTE (Phoenix -> Arize AX)
-----------------------------------
Phoenix and AX share the same OpenTelemetry/OpenInference foundation, so the
*instrumentation* (span writing, retry-loop wrapping, parent/child structure) is
backend-agnostic and unchanged by the migration. Only this read-back query differs.
To switch backends:
  1. Implement `triage/memory/backends/ax.py:fetch_prior_run_history` (same
     `list[PriorAttempt]` contract as the Phoenix adapter).
  2. Set `TRACE_BACKEND = "ax"` below.
Do NOT change the collector endpoint, API keys, or `phoenix.otel.register` call from
here — that configuration is owned by the migration, not by this seam.
"""
from __future__ import annotations

from triage.memory.types import PriorAttempt

# Active trace-query backend. Instrumentation still writes to Phoenix today; the
# migration flips this to "ax" once backends/ax.py is wired. This is the ONE place
# the backend is selected.
TRACE_BACKEND = "phoenix"


def fetch_prior_run_history(cfg, *, issue_url: str, limit: int = 5) -> list[PriorAttempt]:
    """Return prior-run attempt history for `issue_url` from the active backend.

    May raise (network / auth / NotImplementedError for an unwired backend) — the
    caller (`triage.memory.load_learned_context`) guards it and degrades to the
    proven inner loop. This is the single dispatch point for backend selection.
    """
    if TRACE_BACKEND == "phoenix":
        from triage.memory.backends.phoenix import fetch_prior_run_history as _fetch
    elif TRACE_BACKEND == "ax":
        from triage.memory.backends.ax import fetch_prior_run_history as _fetch
    else:  # pragma: no cover - guards a misconfiguration
        raise ValueError(f"unknown TRACE_BACKEND: {TRACE_BACKEND!r}")
    return _fetch(cfg, issue_url=issue_url, limit=limit)
