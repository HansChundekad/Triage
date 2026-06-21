"""Backend-agnostic seam for reading prior-run history out of the trace backend.

7.5's learned-context injection depends ONLY on `fetch_prior_run_history` returning
a `list[PriorAttempt]`. The actual trace-query is surface-specific (it differs
between open-source Phoenix and Arize AX), so it lives behind this single function —
swapping backends is one change here, not scattered through the codebase.

BACKEND SELECTION (Phoenix -> Arize AX migration, done)
-------------------------------------------------------
Phoenix and AX share the same OpenTelemetry/OpenInference foundation, so the
*instrumentation* (span writing, retry-loop wrapping, parent/child structure) is
backend-agnostic. Only this read-back query differs between surfaces. The active
backend is **Arize AX** by default; it is selected per-call from
`cfg.trace_backend` (env `TRIAGE_TRACE_BACKEND`), falling back to the module
default `TRACE_BACKEND`. Set `TRIAGE_TRACE_BACKEND=phoenix` to use the Phoenix
adapter as a fallback. The collector endpoint / API keys / tracer registration are
owned by `triage.tracing.setup`, not by this seam.
"""
from __future__ import annotations

from triage.memory.types import PriorAttempt

# Default trace-query backend (overridable per-call via cfg.trace_backend). AX is
# the primary surface the Arize sponsor judges; phoenix remains a fallback.
TRACE_BACKEND = "ax"


def fetch_prior_run_history(cfg, *, issue_url: str, limit: int = 5) -> list[PriorAttempt]:
    """Return prior-run attempt history for `issue_url` from the active backend.

    The backend is `cfg.trace_backend` when present, else the module default. May
    raise (network / auth / unwired backend) — the caller
    (`triage.memory.load_learned_context`) guards it and degrades to the proven
    inner loop. This is the single dispatch point for backend selection.
    """
    backend = getattr(cfg, "trace_backend", None) or TRACE_BACKEND
    if backend == "ax":
        from triage.memory.backends.ax import fetch_prior_run_history as _fetch
    elif backend == "phoenix":
        from triage.memory.backends.phoenix import fetch_prior_run_history as _fetch
    else:  # pragma: no cover - guards a misconfiguration
        raise ValueError(f"unknown trace backend: {backend!r}")
    return _fetch(cfg, issue_url=issue_url, limit=limit)
