"""Distill prior-run history into one honest, concrete learned-context hint."""
from __future__ import annotations

from collections import defaultdict

from triage.memory.query import PriorAttempt


def distill_hint(prior: list[PriorAttempt]) -> str | None:
    """One-line hint from prior attempts, or None if there's no history.

    Honest by construction: reports run count and whether attempt 1 historically
    reproduced. When most runs failed on attempt 1, appends a generic precondition
    nudge (the Parser turns it into concrete steps); never fabricates a specific fix.
    """
    if not prior:
        return None

    by_run: dict[str, list[PriorAttempt]] = defaultdict(list)
    for a in prior:
        by_run[a.run_id].append(a)

    n_runs = len(by_run)
    attempt1_reproduced = 0
    for attempts in by_run.values():
        first = min(attempts, key=lambda a: a.attempt_number)
        if first.reproduced:
            attempt1_reproduced += 1

    base = (
        f"Prior-run memory: across {n_runs} past run(s) of this issue, "
        f"attempt 1 reproduced in {attempt1_reproduced}/{n_runs}."
    )
    if attempt1_reproduced < n_runs:
        base += (
            " Runs that failed on attempt 1 only reproduced after a retry — "
            "establish the necessary preconditions before the failing action on "
            "attempt 1 instead of discovering them through a failure."
        )
    return base
