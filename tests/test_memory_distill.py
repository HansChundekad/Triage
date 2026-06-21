from triage.memory.distill import distill_hint
from triage.memory.query import PriorAttempt


def _run(run_id, outcomes):
    # outcomes: list of (attempt_number, reproduced)
    return [
        PriorAttempt(run_id=run_id, attempt_number=n,
                     fidelity_label="reproduced" if r else "not_reproduced",
                     fidelity_score=1.0 if r else 0.0, reproduced=r)
        for n, r in outcomes
    ]


def test_empty_history_returns_none():
    assert distill_hint([]) is None


def test_fail_first_pattern_yields_precondition_nudge():
    # 2 runs, both: attempt 1 failed, attempt 2 reproduced.
    prior = _run("A", [(1, False), (2, True)]) + _run("B", [(1, False), (2, True)])
    hint = distill_hint(prior)
    assert hint is not None
    assert "2" in hint                       # n runs surfaced honestly
    assert "attempt 1" in hint.lower()
    assert "precondition" in hint.lower()    # generic nudge present


def test_first_try_success_states_it_without_nudge():
    prior = _run("A", [(1, True)]) + _run("B", [(1, True)])
    hint = distill_hint(prior)
    assert hint is not None
    assert "precondition" not in hint.lower()  # nothing to warn about
    assert "attempt 1" in hint.lower()


def test_hint_is_single_line():
    prior = _run("A", [(1, False), (2, True)])
    assert "\n" not in distill_hint(prior)
