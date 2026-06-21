"""Read prior-run `repro_attempt` history from Phoenix (read-only).

Uses the same `phoenix.client` surface as triage.eval.run_eval. The pure
`parse_prior_attempts` does all the shaping (network-free, unit-tested); the thin
`query_prior_runs` wrapper does the two live fetches and may raise — every caller
guards it (see triage.memory.load_learned_context).
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

PROJECT_IDENTIFIER = "triage-bug-repro"
REPRO_ATTEMPT_SPAN_NAME = "repro_attempt"
RUN_ROOT_SPAN_NAME = "triage_run"
ATTEMPT_NUMBER_ATTR = "attributes.attempt.number"
ISSUE_URL_ATTR = "attributes.github.issue_url"


@dataclass(frozen=True)
class PriorAttempt:
    run_id: str
    attempt_number: int
    fidelity_label: str
    fidelity_score: float | None
    reproduced: bool


def parse_prior_attempts(
    spans_df: pd.DataFrame,
    fidelity_by_span: dict[str, tuple[str, float | None]],
    *,
    issue_url: str | None = None,
    limit: int = 5,
) -> list[PriorAttempt]:
    """Shape raw spans + fidelity annotations into PriorAttempt rows. Pure."""
    if spans_df is None or len(spans_df) == 0:
        return []

    # Map trace_id -> issue_url from the triage_run root rows.
    issue_by_trace: dict[str, str] = {}
    run_start: dict[str, str] = {}
    for _, row in spans_df.iterrows():
        if row.get("name") == RUN_ROOT_SPAN_NAME:
            trace = row.get("context.trace_id")
            issue_by_trace[trace] = row.get(ISSUE_URL_ATTR)
            run_start[trace] = str(row.get("start_time") or "")

    # Collect repro_attempt rows, filtered by issue when requested.
    attempts: list[PriorAttempt] = []
    for span_id, row in spans_df.iterrows():
        if row.get("name") != REPRO_ATTEMPT_SPAN_NAME:
            continue
        trace = row.get("context.trace_id")
        if issue_url is not None and issue_by_trace.get(trace) != issue_url:
            continue
        number = row.get(ATTEMPT_NUMBER_ATTR)
        if number is None:
            continue
        label, score = fidelity_by_span.get(str(span_id), ("", None))
        attempts.append(PriorAttempt(
            run_id=str(trace),
            attempt_number=int(number),
            fidelity_label=label or "",
            fidelity_score=score,
            reproduced=(label == "reproduced"),
        ))

    # Keep only the `limit` most-recent runs (by run root start_time).
    runs_newest_first = sorted(
        {a.run_id for a in attempts},
        key=lambda r: run_start.get(r, ""),
        reverse=True,
    )
    keep = set(runs_newest_first[:limit])
    return [a for a in attempts if a.run_id in keep]


def query_prior_runs(cfg, *, issue_url: str, limit: int = 5) -> list[PriorAttempt]:
    """Live: fetch repro_attempt spans + fidelity annotations, then parse. May raise."""
    from phoenix.client import Client

    client = Client()
    spans_df = client.spans.get_spans_dataframe(project_identifier=PROJECT_IDENTIFIER)
    if spans_df is None or len(spans_df) == 0:
        return []

    attempt_ids = [
        str(sid) for sid, row in spans_df.iterrows()
        if row.get("name") == REPRO_ATTEMPT_SPAN_NAME
    ]
    fidelity_by_span: dict[str, tuple[str, float | None]] = {}
    if attempt_ids:
        ann = client.spans.get_span_annotations_dataframe(
            span_ids=attempt_ids, project_identifier=PROJECT_IDENTIFIER,
        )
        for _, r in ann.iterrows():
            if r.get("annotation_name") != "repro_fidelity":
                continue
            sid = r.get("span_id")
            score = r.get("result.score")
            label = r.get("result.label") or ""
            fidelity_by_span[str(sid)] = (label, None if score is None else float(score))

    return parse_prior_attempts(spans_df, fidelity_by_span, issue_url=issue_url, limit=limit)
