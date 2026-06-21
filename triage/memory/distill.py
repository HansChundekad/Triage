"""Distill prior-run history into one honest, concrete learned-context hint."""
from __future__ import annotations

from collections import defaultdict

from triage.memory.query import PriorAttempt


def distill_hint(prior: list[PriorAttempt]) -> str | None:
    """One-line hint from prior attempts, or None if there's no history.

    Honest by construction: reports run count and whether the first attempt
    historically reproduced. When a run's first attempt failed, appends a generic
    precondition nudge (the Parser turns it into concrete steps); never fabricates
    a specific fix.

    The "first attempt" of each run is the earliest by ``start_time`` — NOT the
    lowest ``attempt_number``, which is unreliable (a ``redirect_parser`` re-parse
    resets the counter, so two attempts in one run can both report number 1).
    """
    if not prior:
        return None

    by_run: dict[str, list[PriorAttempt]] = defaultdict(list)
    for a in prior:
        by_run[a.run_id].append(a)

    n_runs = len(by_run)
    attempt1_reproduced = 0
    for attempts in by_run.values():
        first = min(attempts, key=lambda a: a.start_time)
        if first.reproduced:
            attempt1_reproduced += 1

    base = (
        f"Prior-run memory: across {n_runs} past run(s) of this issue, "
        f"the first attempt reproduced in {attempt1_reproduced}/{n_runs}."
    )
    if attempt1_reproduced < n_runs:
        base += (
            " Runs whose first attempt failed only reproduced after a retry — "
            "establish the necessary preconditions before the failing action on "
            "the first attempt instead of discovering them through a failure."
        )
    return base
