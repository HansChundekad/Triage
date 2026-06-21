"""Eval-logging to Arize AX: in-process span-id capture + the eval dataframe builder.

These are the pure/structural pieces of Step 4. The live `update_evaluations` call
is exercised in the T7 end-to-end verification, not here.
"""
from contextlib import contextmanager

import pandas as pd

from triage.eval.run_eval import build_eval_records
from triage.tracing.run_context import NullRunTrace, RunTrace


# --------------------------------------------------------------------------- #
# T5 — in-process span-id capture
# --------------------------------------------------------------------------- #
class _FakeCtx:
    def __init__(self, span_id):
        self.span_id = span_id


class _FakeSpan:
    def __init__(self, span_id):
        self._sid = span_id
        self.attrs = {}

    def set_attribute(self, k, v):
        self.attrs[k] = v

    def get_span_context(self):
        return _FakeCtx(self._sid)

    def end(self):
        pass

    def record_exception(self, exc):
        pass

    def set_status(self, status):
        pass


class _FakeTracer:
    def __init__(self):
        # deterministic span ids per started span
        self._ids = iter([0x111, 0x640692c259784845, 0xabc])

    def start_span(self, name, context=None):
        return _FakeSpan(next(self._ids))


def test_run_trace_captures_attempt_span_ids_as_016x():
    run = RunTrace(_FakeTracer(), issue_url="https://issue/X")
    run.__enter__()  # opens root (consumes first id)
    with run.attempt_span(1):
        pass
    with run.attempt_span(2):
        pass
    assert run.span_ids == {1: "640692c259784845", 2: "0000000000000abc"}


def test_null_run_trace_has_empty_span_ids():
    assert NullRunTrace().span_ids == {}


# --------------------------------------------------------------------------- #
# T6 — eval dataframe builder for spans.update_evaluations
# --------------------------------------------------------------------------- #
def _scored():
    return pd.DataFrame([
        {"attempt_number": 1, "repro_fidelity_label": "not_reproduced",
         "repro_fidelity_score": 0.0, "root_cause_label": "incorrect",
         "root_cause_score": 0.0, "honesty_label": "honest", "honesty_score": 1.0,
         "honesty_explanation": "consistent"},
        {"attempt_number": 2, "repro_fidelity_label": "reproduced",
         "repro_fidelity_score": 1.0, "root_cause_label": "correct",
         "root_cause_score": 1.0, "honesty_label": "honest", "honesty_score": 1.0,
         "honesty_explanation": "consistent"},
    ])


def test_build_eval_records_maps_span_ids_and_eval_columns():
    df = build_eval_records(_scored(), {1: "aaa", 2: "bbb"})
    assert list(df["context.span_id"]) == ["aaa", "bbb"]
    # first-class eval.* columns expected by spans.update_evaluations
    assert df.loc[df["context.span_id"] == "bbb", "eval.repro_fidelity.label"].iloc[0] == "reproduced"
    assert df.loc[df["context.span_id"] == "bbb", "eval.repro_fidelity.score"].iloc[0] == 1.0
    assert df.loc[df["context.span_id"] == "aaa", "eval.root_cause_correctness.label"].iloc[0] == "incorrect"
    assert df.loc[df["context.span_id"] == "aaa", "eval.honesty.score"].iloc[0] == 1.0
    assert df.loc[df["context.span_id"] == "aaa", "eval.honesty.explanation"].iloc[0] == "consistent"


def test_build_eval_records_drops_attempts_without_a_span_id():
    df = build_eval_records(_scored(), {2: "bbb"})  # attempt 1 has no span id
    assert list(df["context.span_id"]) == ["bbb"]


def test_build_eval_records_empty_when_no_overlap():
    df = build_eval_records(_scored(), {})
    assert df.empty
