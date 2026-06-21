"""Trace-query backend adapters for the learned-context read-back.

Each adapter exposes `fetch_prior_run_history(cfg, *, issue_url, limit) ->
list[PriorAttempt]` and is selected by `triage.memory.history.TRACE_BACKEND`.
`phoenix` is implemented and live-verified; `ax` is a stub for the migration agent.
"""
