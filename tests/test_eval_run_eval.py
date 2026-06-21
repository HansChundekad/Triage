"""Unit tests for the pure helpers in triage.eval.run_eval.

Only the pure functions are tested — no live LLM/Phoenix calls.
"""
from __future__ import annotations

import json

import pandas as pd

from triage.eval.run_eval import build_eval_dataframe, parse_score_column


def test_build_eval_dataframe_one_row_per_attempt():
    attempts = [
        {"attempt": 1, "bug_detected": False, "evidence": ["empty"], "console_errors": []},
        {"attempt": 2, "bug_detected": True, "evidence": ["blank"],
         "console_errors": ["Cannot read properties of undefined"]},
    ]
    df = build_eval_dataframe(attempts, issue_text="app blanks on delete",
                              hypothesis_root_cause="reads items[0] after delete")
    assert list(df["attempt_number"]) == [1, 2]
    assert "app blanks on delete" in df.iloc[0]["input"]
    # fidelity output column reflects the per-attempt verdict
    assert "BUG NOT REPRODUCED" in df.iloc[0]["fidelity_output"]
    assert "BUG REPRODUCED" in df.iloc[1]["fidelity_output"]
    # root-cause columns carry ground truth + hypothesis
    assert "reads items[0] after delete" in df.iloc[0]["root_cause_output"]
    assert df.iloc[0]["root_cause_reference"]  # planted-bug ground truth present
    assert list(df["bug_detected"]) == [False, True]


def test_parse_score_column_extracts_label_and_score_from_json():
    col = "repro_fidelity_score"
    df = pd.DataFrame({
        col: [
            json.dumps({"name": "repro_fidelity", "score": 0.0,
                        "label": "not_reproduced", "explanation": "no crash",
                        "kind": "llm"}),
            json.dumps({"name": "repro_fidelity", "score": 1.0,
                        "label": "reproduced", "explanation": "blank page",
                        "kind": "llm"}),
        ],
    })
    labels, scores = parse_score_column(df, col)
    assert labels == ["not_reproduced", "reproduced"]
    assert scores == [0.0, 1.0]


def test_parse_score_column_handles_missing_cells():
    col = "root_cause_correctness_score"
    df = pd.DataFrame({col: [None, float("nan")]})
    labels, scores = parse_score_column(df, col)
    assert labels == ["", ""]
    assert scores == [None, None]
