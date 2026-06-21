"""Read prior-run `repro_attempt` history from Phoenix (read-only).

Uses the same `phoenix.client` surface as triage.eval.run_eval. The pure
`parse_prior_attempts` does all the shaping (network-free, unit-tested); the thin
`query_prior_runs` wrapper does the live fetch and may raise — every caller
guards it (see triage.memory.load_learned_context).

Trace shape (verified live against Phoenix project `triage-bug-repro`):
- The spans dataframe is indexed by `context.span_id` (string).
- OTEL attributes arrive as NESTED dicts under flattened columns, e.g.
  `attributes.attempt` == {"number": 1}, `attributes.bug` == {"detected": True},
  and on the `triage_run` root `attributes.github` == {"issue_url": "..."}.
- The honest reproduction signal is `attributes.bug.detected` on each
  `repro_attempt` span (rule 8's fail→succeed flip). The `repro_fidelity`
  annotation is only sometimes present (the booth path does not log it), so it is
  treated as OPTIONAL enrichment — never the primary signal.
- `attributes.attempt.number` is UNRELIABLE for ordering: a `redirect_parser`
  re-parse resets the counter, so two real attempts in one run can both report
  number == 1. Within-run ordering therefore uses `start_time`, not the number.
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

PROJECT_IDENTIFIER = "triage-bug-repro"
REPRO_ATTEMPT_SPAN_NAME = "repro_attempt"
RUN_ROOT_SPAN_NAME = "triage_run"


@dataclass(frozen=True)
class PriorAttempt:
    run_id: str                 # context.trace_id of the run this attempt belongs to
    attempt_number: int         # attributes.attempt.number (may collide across redirects)
    start_time: str             # honest within-run ordering key (number is unreliable)
    reproduced: bool            # attributes.bug.detected — the honest rule-8 signal
    fidelity_label: str         # optional enrichment from the repro_fidelity annotation
    fidelity_score: float | None


def _nested(row, attr: str, key: str):
    """Read row[`attributes.<attr>`][`key`], tolerating missing / NaN cells. Pure."""
    d = row.get(f"attributes.{attr}")
    if isinstance(d, dict):
        return d.get(key)
    return None


def parse_prior_attempts(
    spans_df: pd.DataFrame,
    fidelity_by_span: dict[str, tuple[str, float | None]],
    *,
    issue_url: str | None = None,
    limit: int = 5,
) -> list[PriorAttempt]:
    """Shape raw spans (+ optional fidelity annotations) into PriorAttempt rows. Pure."""
    if spans_df is None or len(spans_df) == 0:
        return []

    # Map trace_id -> issue_url + run start from the triage_run root rows.
    issue_by_trace: dict[str, str] = {}
    run_start: dict[str, str] = {}
    for _, row in spans_df.iterrows():
        if row.get("name") == RUN_ROOT_SPAN_NAME:
            trace = row.get("context.trace_id")
            issue_by_trace[trace] = _nested(row, "github", "issue_url")
            run_start[trace] = str(row.get("start_time") or "")

    # Collect repro_attempt rows, filtered by issue when requested.
    attempts: list[PriorAttempt] = []
    for span_id, row in spans_df.iterrows():
        if row.get("name") != REPRO_ATTEMPT_SPAN_NAME:
            continue
        trace = row.get("context.trace_id")
        if issue_url is not None and issue_by_trace.get(trace) != issue_url:
            continue
        number = _nested(row, "attempt", "number")
        if number is None:
            continue
        # Primary, always-present honest signal: attributes.bug.detected.
        detected = _nested(row, "bug", "detected")
        label, score = fidelity_by_span.get(str(span_id), ("", None))
        if detected is not None:
            reproduced = bool(detected)
        else:  # fall back to the optional fidelity annotation if bug.detected is absent
            reproduced = (label == "reproduced")
        attempts.append(PriorAttempt(
            run_id=str(trace),
            attempt_number=int(number),
            start_time=str(row.get("start_time") or ""),
            reproduced=reproduced,
            fidelity_label=label or "",
            fidelity_score=score,
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
    """Live: fetch repro_attempt spans (+ best-effort fidelity annotations), then parse.

    May raise (network/auth) — the caller (load_learned_context) guards it. The
    annotation fetch is best-effort: if it errors or returns nothing, history is
    still derived from the spans' `bug.detected` signal.
    """
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
        try:
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
        except Exception:  # noqa: BLE001 — annotations are optional enrichment
            fidelity_by_span = {}

    return parse_prior_attempts(spans_df, fidelity_by_span, issue_url=issue_url, limit=limit)
