import pandas as pd

from triage.memory.backends.phoenix import parse_prior_attempts


def _spans_df():
    # Real Phoenix shape: indexed by context.span_id; OTEL attributes arrive as
    # NESTED dicts under flattened columns (attributes.attempt == {"number": n},
    # attributes.bug == {"detected": bool}, attributes.github == {"issue_url": ...}).
    # Two runs of issue X (trace A) + B and one of a DIFFERENT issue (trace C).
    rows = [
        # trace A — issue X: first attempt failed, second reproduced
        {"id": "rootA", "name": "triage_run", "context.trace_id": "A",
         "parent_id": None, "start_time": "2026-06-20T10:00:00Z",
         "attributes.github": {"issue_url": "https://issue/X"},
         "attributes.attempt": None, "attributes.bug": None},
        {"id": "a1", "name": "repro_attempt", "context.trace_id": "A",
         "parent_id": "rootA", "start_time": "2026-06-20T10:00:01Z",
         "attributes.github": None,
         "attributes.attempt": {"number": 1}, "attributes.bug": {"detected": False}},
        {"id": "a2", "name": "repro_attempt", "context.trace_id": "A",
         "parent_id": "rootA", "start_time": "2026-06-20T10:00:02Z",
         "attributes.github": None,
         "attributes.attempt": {"number": 2}, "attributes.bug": {"detected": True}},
        # trace C — different issue, filtered out when issue_url=X
        {"id": "rootC", "name": "triage_run", "context.trace_id": "C",
         "parent_id": None, "start_time": "2026-06-20T09:00:00Z",
         "attributes.github": {"issue_url": "https://issue/OTHER"},
         "attributes.attempt": None, "attributes.bug": None},
        {"id": "c1", "name": "repro_attempt", "context.trace_id": "C",
         "parent_id": "rootC", "start_time": "2026-06-20T09:00:01Z",
         "attributes.github": None,
         "attributes.attempt": {"number": 1}, "attributes.bug": {"detected": True}},
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


def test_reproduced_derives_from_bug_detected():
    out = parse_prior_attempts(_spans_df(), _fidelity(), issue_url="https://issue/X")
    a2 = next(a for a in out if a.attempt_number == 2)
    assert a2.reproduced is True
    a1 = next(a for a in out if a.attempt_number == 1)
    assert a1.reproduced is False


def test_bug_detected_overrides_fidelity_label():
    # bug.detected is the PRIMARY honest signal: even if an annotation disagrees,
    # bug.detected wins. Here a1's bug.detected is False but fidelity says reproduced.
    misleading = {"a1": ("reproduced", 1.0)}
    out = parse_prior_attempts(_spans_df(), misleading, issue_url="https://issue/X")
    a1 = next(a for a in out if a.attempt_number == 1)
    assert a1.reproduced is False  # bug.detected=False overrides the annotation


def test_fidelity_label_score_captured_as_enrichment():
    out = parse_prior_attempts(_spans_df(), _fidelity(), issue_url="https://issue/X")
    a2 = next(a for a in out if a.attempt_number == 2)
    assert a2.fidelity_label == "reproduced" and a2.fidelity_score == 1.0


def test_falls_back_to_fidelity_when_bug_attr_absent():
    # A repro_attempt span with no attributes.bug must fall back to the fidelity label.
    rows = [
        {"id": "rootZ", "name": "triage_run", "context.trace_id": "Z",
         "parent_id": None, "start_time": "2026-06-20T11:00:00Z",
         "attributes.github": {"issue_url": "https://issue/X"},
         "attributes.attempt": None, "attributes.bug": None},
        {"id": "z1", "name": "repro_attempt", "context.trace_id": "Z",
         "parent_id": "rootZ", "start_time": "2026-06-20T11:00:01Z",
         "attributes.github": None,
         "attributes.attempt": {"number": 1}, "attributes.bug": None},
    ]
    df = pd.DataFrame(rows).set_index("id")
    repro = parse_prior_attempts(df, {"z1": ("reproduced", 1.0)}, issue_url="https://issue/X")
    assert repro[0].reproduced is True
    none = parse_prior_attempts(df, {}, issue_url="https://issue/X")
    assert none[0].reproduced is False and none[0].fidelity_label == ""


def test_no_issue_filter_returns_all_repro_attempts():
    out = parse_prior_attempts(_spans_df(), _fidelity(), issue_url=None)
    assert {a.run_id for a in out} == {"A", "C"}


def test_limit_keeps_most_recent_runs():
    out = parse_prior_attempts(_spans_df(), _fidelity(), issue_url=None, limit=1)
    # trace A is newer (root 10:00) than trace C (root 09:00) → only A survives.
    assert {a.run_id for a in out} == {"A"}


def test_start_time_is_populated_for_ordering():
    out = parse_prior_attempts(_spans_df(), _fidelity(), issue_url="https://issue/X")
    a1 = next(a for a in out if a.attempt_number == 1)
    a2 = next(a for a in out if a.attempt_number == 2)
    assert a1.start_time < a2.start_time  # honest within-run ordering key
