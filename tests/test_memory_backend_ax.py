"""Pure-parser tests for the Arize AX read backend.

Fixtures match the REAL `ax spans export` JSON shape verified live (2026-06-21):
- a span is a dict with top-level `name`, `start_time`, `parent_id`, and nested
  `context` ({"trace_id":..., "span_id":...});
- `attributes` is a FLAT dict with DOTTED keys: "attempt.number", "bug.detected",
  "github.issue_url" (unlike Phoenix, which nests them as sub-dicts).
"""
from triage.memory.backends.ax import parse_prior_attempts


def _spans():
    return [
        # trace A — issue X: attempt 1 failed, attempt 2 reproduced (honest flip)
        {"name": "triage_run", "context": {"trace_id": "A", "span_id": "rootA"},
         "parent_id": None, "start_time": "2026-06-20T10:00:00Z",
         "attributes": {"github.issue_url": "https://issue/X", "app.url": "u"}},
        {"name": "repro_attempt", "context": {"trace_id": "A", "span_id": "a1"},
         "parent_id": "rootA", "start_time": "2026-06-20T10:00:01Z",
         "attributes": {"attempt.number": 1, "bug.detected": False,
                        "github.issue_url": "https://issue/X"}},
        {"name": "repro_attempt", "context": {"trace_id": "A", "span_id": "a2"},
         "parent_id": "rootA", "start_time": "2026-06-20T10:00:02Z",
         "attributes": {"attempt.number": 2, "bug.detected": True,
                        "github.issue_url": "https://issue/X",
                        "eval.repro_fidelity.label": "reproduced",
                        "eval.repro_fidelity.score": 1.0}},
        # trace C — different issue (filtered out when issue_url=X)
        {"name": "triage_run", "context": {"trace_id": "C", "span_id": "rootC"},
         "parent_id": None, "start_time": "2026-06-20T09:00:00Z",
         "attributes": {"github.issue_url": "https://issue/OTHER"}},
        {"name": "repro_attempt", "context": {"trace_id": "C", "span_id": "c1"},
         "parent_id": "rootC", "start_time": "2026-06-20T09:00:01Z",
         "attributes": {"attempt.number": 1, "bug.detected": True,
                        "github.issue_url": "https://issue/OTHER"}},
    ]


def test_empty_input_returns_empty():
    assert parse_prior_attempts([], issue_url="https://issue/X") == []


def test_parses_attempts_for_matching_issue_only():
    out = parse_prior_attempts(_spans(), issue_url="https://issue/X")
    assert {a.run_id for a in out} == {"A"}
    assert sorted((a.attempt_number, a.reproduced) for a in out) == [(1, False), (2, True)]


def test_reproduced_derives_from_bug_detected():
    out = parse_prior_attempts(_spans(), issue_url="https://issue/X")
    a1 = next(a for a in out if a.attempt_number == 1)
    a2 = next(a for a in out if a.attempt_number == 2)
    assert a1.reproduced is False and a2.reproduced is True


def test_fidelity_label_score_captured_as_enrichment_when_present():
    out = parse_prior_attempts(_spans(), issue_url="https://issue/X")
    a2 = next(a for a in out if a.attempt_number == 2)
    assert a2.fidelity_label == "reproduced" and a2.fidelity_score == 1.0
    a1 = next(a for a in out if a.attempt_number == 1)
    assert a1.fidelity_label == "" and a1.fidelity_score is None


def test_no_issue_filter_returns_all_repro_attempts():
    out = parse_prior_attempts(_spans(), issue_url=None)
    assert {a.run_id for a in out} == {"A", "C"}


def test_limit_keeps_most_recent_runs():
    out = parse_prior_attempts(_spans(), issue_url=None, limit=1)
    assert {a.run_id for a in out} == {"A"}  # trace A (10:00) newer than C (09:00)


def test_start_time_populated_for_ordering():
    out = parse_prior_attempts(_spans(), issue_url="https://issue/X")
    a1 = next(a for a in out if a.attempt_number == 1)
    a2 = next(a for a in out if a.attempt_number == 2)
    assert a1.start_time < a2.start_time
