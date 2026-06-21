"""Per-attempt scoring + logging onto repro_attempt spans (modern phoenix.client).

DRIFT NOTE (arize-phoenix-evals 3.1.0 / arize-phoenix-client 2.9.0):
`evaluate_dataframe(dataframe, evaluators)` does NOT return flat label/score
columns. For each evaluator it appends:
  - "{score_name}_score" — a JSON-serialized Score object (a JSON string with
    keys name/score/label/explanation/metadata/direction/kind), and
  - "{evaluator_name}_execution_details".
`score_name` equals the evaluator's `name`, so the columns are
`repro_fidelity_score` and `root_cause_correctness_score`. We therefore
`json.loads` each cell to recover label + score (see `parse_score_column`).
"""
from __future__ import annotations

import json
import math

import pandas as pd

from triage.eval.code_checks import honesty_check
from triage.eval.judges import (
    build_fidelity_input,
    build_judge_llm,
    build_root_cause_input,
    make_fidelity_judge,
    make_root_cause_judge,
)

PROJECT_IDENTIFIER = "triage-bug-repro"
REPRO_ATTEMPT_SPAN_NAME = "repro_attempt"
ATTEMPT_NUMBER_ATTR = "attempt.number"


# --------------------------------------------------------------------------- #
# Pure helpers (unit-tested)
# --------------------------------------------------------------------------- #
def build_eval_dataframe(attempts, issue_text, hypothesis_root_cause) -> pd.DataFrame:
    """One row per attempt with judge-input columns. Pure."""
    rows = []
    for a in attempts:
        fid = build_fidelity_input(issue_text, a)
        rc = build_root_cause_input(issue_text, hypothesis_root_cause)
        rows.append({
            "attempt_number": a["attempt"],
            "input": issue_text,
            "fidelity_output": fid["output"],
            "root_cause_reference": rc["reference"],
            "root_cause_output": rc["output"],
            "bug_detected": a.get("bug_detected", False),
        })
    return pd.DataFrame(rows)


def parse_score_column(results_df: pd.DataFrame, col: str) -> tuple[list[str], list[float]]:
    """Extract (labels, scores) from a `{name}_score` column of JSON Score dicts.

    Each cell is a JSON-serialized phoenix Score (`{"label":..., "score":...}`).
    A missing / None / NaN cell yields label "" and score None. Pure.
    """
    labels: list[str] = []
    scores: list[float] = []
    for cell in results_df[col].tolist():
        if cell is None or (isinstance(cell, float) and math.isnan(cell)):
            labels.append("")
            scores.append(None)
            continue
        data = json.loads(cell) if isinstance(cell, str) else dict(cell)
        labels.append(data.get("label") or "")
        scores.append(data.get("score"))
    return labels, scores


# --------------------------------------------------------------------------- #
# Live, thin orchestration
# --------------------------------------------------------------------------- #
def score_attempts(df, *, fidelity_judge, root_cause_judge):
    """Run each judge via evaluate_dataframe; extract labels/scores via parse_score_column."""
    from phoenix.evals import evaluate_dataframe

    # Map our columns into each judge's template input keys, then evaluate.
    fid_df = df.rename(columns={"fidelity_output": "output"})[["input", "output"]]
    rc_df = df.rename(columns={
        "root_cause_output": "output",
        "root_cause_reference": "reference",
    })[["input", "reference", "output"]]

    fid_results = evaluate_dataframe(fid_df, [fidelity_judge])
    rc_results = evaluate_dataframe(rc_df, [root_cause_judge])

    fid_labels, fid_scores = parse_score_column(fid_results, "repro_fidelity_score")
    rc_labels, rc_scores = parse_score_column(rc_results, "root_cause_correctness_score")

    out = df.copy()
    out["repro_fidelity_label"] = fid_labels
    out["repro_fidelity_score"] = fid_scores
    out["root_cause_label"] = rc_labels
    out["root_cause_score"] = rc_scores
    return out


def run_eval(cfg, repro_state, artifacts, *, span_lookup=None, hypothesis_root_cause=""):
    """Load attempts → build df → score → add honesty → log onto repro_attempt spans."""
    attempts = artifacts.load_attempts()
    if not attempts:
        return pd.DataFrame()

    issue_text = getattr(cfg, "github_issue_url", "")
    df = build_eval_dataframe(attempts, issue_text, hypothesis_root_cause)

    llm = build_judge_llm(cfg)
    scored = score_attempts(
        df,
        fidelity_judge=make_fidelity_judge(llm),
        root_cause_judge=make_root_cause_judge(llm),
    )

    # honesty (code) eval per attempt — needs the dual-signal booleans; fall back
    # so an attempt lacking them is treated as self-consistent (always honest).
    honesty = [
        honesty_check(
            a.get("bug_detected", False),
            a.get("blank_body", a.get("bug_detected", False)),
            a.get("console_match", a.get("bug_detected", False)),
        )
        for a in attempts
    ]
    scored["honesty_label"] = [h.label for h in honesty]
    scored["honesty_score"] = [h.score for h in honesty]
    scored["honesty_explanation"] = [h.explanation for h in honesty]

    if span_lookup is None:
        span_lookup = _phoenix_span_lookup(cfg)
    _log_to_spans(scored, span_lookup)
    return scored


def _phoenix_span_lookup(cfg):
    """Return {attempt_number: span_id} by querying repro_attempt spans in Phoenix."""
    from phoenix.client import Client

    client = Client()
    spans = client.spans.get_spans_dataframe(
        project_identifier=PROJECT_IDENTIFIER,
    )
    lookup: dict[int, str] = {}
    for span_id, row in spans.iterrows():
        if row.get("name") != REPRO_ATTEMPT_SPAN_NAME:
            continue
        number = row.get(f"attributes.{ATTEMPT_NUMBER_ATTR}")
        if number is None:
            continue
        # span_id is the dataframe index in phoenix.client; fall back to a column.
        sid = span_id if isinstance(span_id, str) else row.get("context.span_id")
        lookup[int(number)] = sid
    return lookup


def _annotation_frame(scored, span_lookup, *, label_col, score_col, explanation_col=None):
    records = []
    for _, r in scored.iterrows():
        sid = span_lookup.get(int(r["attempt_number"]))
        if not sid:
            continue
        score = r[score_col]
        rec = {
            "span_id": sid,
            "label": r[label_col],
            "score": None if score is None else float(score),
        }
        if explanation_col is not None:
            rec["explanation"] = r[explanation_col]
        records.append(rec)
    if not records:
        return None
    return pd.DataFrame(records).set_index("span_id")


def _log_to_spans(scored, span_lookup):
    from phoenix.client import Client

    client = Client()
    plan = [
        ("repro_fidelity", "LLM", "repro_fidelity_label", "repro_fidelity_score", None),
        ("root_cause_correctness", "LLM", "root_cause_label", "root_cause_score", None),
        ("honesty", "CODE", "honesty_label", "honesty_score", "honesty_explanation"),
    ]
    for name, kind, label_col, score_col, expl_col in plan:
        frame = _annotation_frame(
            scored, span_lookup,
            label_col=label_col, score_col=score_col, explanation_col=expl_col,
        )
        if frame is None:
            continue
        client.spans.log_span_annotations_dataframe(
            dataframe=frame, annotation_name=name, annotator_kind=kind,
        )
