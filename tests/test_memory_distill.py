from triage.memory.distill import distill_hint
from triage.memory.types import PriorAttempt


def _run(run_id, outcomes):
    # outcomes: list of (start_time, reproduced). attempt_number is fixed at 1 to
    # mirror the real collision; ordering is by start_time.
    return [
        PriorAttempt(run_id=run_id, attempt_number=1, start_time=t,
                     reproduced=r,
                     fidelity_label="reproduced" if r else "not_reproduced",
                     fidelity_score=1.0 if r else 0.0)
        for t, r in outcomes
    ]


def test_empty_history_returns_none():
    assert distill_hint([]) is None


def test_fail_first_pattern_yields_precondition_nudge():
    # 2 runs, both: first attempt (earlier start) failed, later attempt reproduced.
    prior = (_run("A", [("2026-06-20T10:00:01Z", False), ("2026-06-20T10:00:02Z", True)])
             + _run("B", [("2026-06-20T11:00:01Z", False), ("2026-06-20T11:00:02Z", True)]))
    hint = distill_hint(prior)
    assert hint is not None
    assert "2" in hint                          # n runs surfaced honestly
    assert "first attempt" in hint.lower()
    assert "precondition" in hint.lower()       # generic nudge present


def test_first_try_success_states_it_without_nudge():
    prior = (_run("A", [("2026-06-20T10:00:01Z", True)])
             + _run("B", [("2026-06-20T11:00:01Z", True)]))
    hint = distill_hint(prior)
    assert hint is not None
    assert "precondition" not in hint.lower()   # nothing to warn about
    assert "first attempt" in hint.lower()


def test_first_attempt_is_earliest_start_time_not_lowest_number():
    # Earliest start (…01) reproduced=True but has the HIGHER attempt_number (2);
    # the later attempt (…02) failed with the lower number (1). Ordering must use
    # start_time, so the "first attempt reproduced" count is 1/1 (no nudge).
    prior = [
        PriorAttempt("A", attempt_number=2, start_time="2026-06-20T10:00:01Z",
                     reproduced=True, fidelity_label="reproduced", fidelity_score=1.0),
        PriorAttempt("A", attempt_number=1, start_time="2026-06-20T10:00:02Z",
                     reproduced=False, fidelity_label="not_reproduced", fidelity_score=0.0),
    ]
    hint = distill_hint(prior)
    assert "1/1" in hint
    assert "precondition" not in hint.lower()


def test_hint_is_single_line():
    prior = _run("A", [("2026-06-20T10:00:01Z", False), ("2026-06-20T10:00:02Z", True)])
    assert "\n" not in distill_hint(prior)
