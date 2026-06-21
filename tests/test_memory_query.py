import pandas as pd

from triage.memory.query import PriorAttempt, parse_prior_attempts


def _spans_df():
    # Two runs (trace A, trace B) of the same issue, each a triage_run parent
    # plus repro_attempt children. Plus one run of a DIFFERENT issue (trace C).
    rows = [
        # trace A — issue X: attempt 1 failed, attempt 2 reproduced
        {"id": "rootA", "name": "triage_run", "context.trace_id": "A",
         "parent_id": None, "start_time": "2026-06-20T10:00:00Z",
         "attributes.github.issue_url": "https://issue/X", "attributes.attempt.number": None},
        {"id": "a1", "name": "repro_attempt", "context.trace_id": "A",
         "parent_id": "rootA", "start_time": "2026-06-20T10:00:01Z",
         "attributes.github.issue_url": None, "attributes.attempt.number": 1},
        {"id": "a2", "name": "repro_attempt", "context.trace_id": "A",
         "parent_id": "rootA", "start_time": "2026-06-20T10:00:02Z",
         "attributes.github.issue_url": None, "attributes.attempt.number": 2},
        # trace C — different issue, must be filtered out when issue_url=X
        {"id": "rootC", "name": "triage_run", "context.trace_id": "C",
         "parent_id": None, "start_time": "2026-06-20T09:00:00Z",
         "attributes.github.issue_url": "https://issue/OTHER", "attributes.attempt.number": None},
        {"id": "c1", "name": "repro_attempt", "context.trace_id": "C",
         "parent_id": "rootC", "start_time": "2026-06-20T09:00:01Z",
         "attributes.github.issue_url": None, "attributes.attempt.number": 1},
    ]
    return pd.DataFrame(rows).set_index("id")


def _fidelity():
    return {
        "a1": ("not_reproduced", 0.0),
        "a2": ("reproduced", 1.0),
        "c1": ("reproduced", 1.0),
    }


def test_parses_attempts_for_matching_issue_only():
    out = parse_prior_attempts(_spans_df(), _fidelity(), issue_url="https://issue/X")
    assert {a.run_id for a in out} == {"A"}
    assert sorted((a.attempt_number, a.reproduced) for a in out) == [(1, False), (2, True)]


def test_reproduced_derives_from_fidelity_label():
    out = parse_prior_attempts(_spans_df(), _fidelity(), issue_url="https://issue/X")
    a2 = next(a for a in out if a.attempt_number == 2)
    assert a2.reproduced is True and a2.fidelity_score == 1.0


def test_no_issue_filter_returns_all_repro_attempts():
    out = parse_prior_attempts(_spans_df(), _fidelity(), issue_url=None)
    assert {a.run_id for a in out} == {"A", "C"}


def test_limit_keeps_most_recent_runs():
    out = parse_prior_attempts(_spans_df(), _fidelity(), issue_url=None, limit=1)
    # trace A is newer (10:00) than trace C (09:00) → only A survives.
    assert {a.run_id for a in out} == {"A"}


def test_missing_fidelity_is_not_reproduced():
    out = parse_prior_attempts(_spans_df(), {}, issue_url="https://issue/X")
    assert all(a.reproduced is False and a.fidelity_label == "" for a in out)
