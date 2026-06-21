"""Trace-query backend adapters for the learned-context read-back.

Each adapter exposes `fetch_prior_run_history(cfg, *, issue_url, limit) ->
list[PriorAttempt]` and is selected by `triage.memory.history` from
`cfg.trace_backend`. Both `ax` (primary, Arize AX via the `ax` CLI) and `phoenix`
(fallback) are implemented and live-verified.
"""
