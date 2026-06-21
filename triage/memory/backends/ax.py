"""Arize AX trace-query backend — reads prior-run `repro_attempt` history (read-only).

Selected when `triage.memory.history` resolves the backend to "ax" (the default
after the Phoenix->AX migration). The pure `parse_prior_attempts` does all the
shaping (network-free, unit-tested); `fetch_prior_run_history` shells out to the
`ax` CLI (`ax spans export ... --stdout`) and parses its JSON — the seam's caller
(`triage.memory.load_learned_context`) guards every failure into the inner loop.

AX export shape (verified live against project `triage-bug-repro`, 2026-06-21):
- Each span is a dict: top-level `name`, `start_time`, `parent_id`, nested
  `context` ({"trace_id":..., "span_id":...}), and a FLAT `attributes` dict with
  DOTTED keys: "attempt.number", "bug.detected", "github.issue_url". (This differs
  from Phoenix, which nests attributes as sub-dicts — hence a separate adapter.)
- The honest reproduction signal is `attributes["bug.detected"]` on each
  `repro_attempt` span (rule 8's fail->succeed flip). `eval.repro_fidelity.*` is
  optional enrichment when an evaluation has been logged onto the span.
- `attributes["attempt.number"]` is UNRELIABLE for ordering (a `redirect_parser`
  re-parse resets the counter); within-run ordering uses `start_time`.

This module owns the AX read surface. It does NOT touch the collector endpoint,
API keys, or the tracer registration — those belong to `triage.tracing.setup`.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

from triage.memory.types import PriorAttempt

PROJECT_NAME = "triage-bug-repro"
REPRO_ATTEMPT_SPAN_NAME = "repro_attempt"
RUN_ROOT_SPAN_NAME = "triage_run"
_AX_QUERY_TIMEOUT_S = 30


def _attr(span: dict, key: str):
    """Read span['attributes'][key] from the flat dotted AX attribute dict. Pure."""
    attrs = span.get("attributes")
    if isinstance(attrs, dict):
        return attrs.get(key)
    return None


def _trace_id(span: dict):
    ctx = span.get("context")
    if isinstance(ctx, dict):
        return ctx.get("trace_id")
    return span.get("context.trace_id")


def parse_prior_attempts(
    spans: list[dict],
    *,
    issue_url: str | None = None,
    limit: int = 5,
) -> list[PriorAttempt]:
    """Shape raw AX span dicts into PriorAttempt rows. Pure (network-free)."""
    if not spans:
        return []

    # Map trace_id -> issue_url + run start from the triage_run root rows.
    issue_by_trace: dict[str, str] = {}
    run_start: dict[str, str] = {}
    for span in spans:
        if span.get("name") == RUN_ROOT_SPAN_NAME:
            trace = _trace_id(span)
            issue_by_trace[trace] = _attr(span, "github.issue_url")
            run_start[trace] = str(span.get("start_time") or "")

    attempts: list[PriorAttempt] = []
    for span in spans:
        if span.get("name") != REPRO_ATTEMPT_SPAN_NAME:
            continue
        trace = _trace_id(span)
        # Prefer the run root's issue; fall back to the attempt's own attribute.
        span_issue = issue_by_trace.get(trace) or _attr(span, "github.issue_url")
        if issue_url is not None and span_issue != issue_url:
            continue
        number = _attr(span, "attempt.number")
        if number is None:
            continue
        detected = _attr(span, "bug.detected")
        label = _attr(span, "eval.repro_fidelity.label") or ""
        score = _attr(span, "eval.repro_fidelity.score")
        if detected is not None:
            reproduced = bool(detected)
        else:  # fall back to the optional fidelity annotation
            reproduced = (label == "reproduced")
        attempts.append(PriorAttempt(
            run_id=str(trace),
            attempt_number=int(number),
            start_time=str(span.get("start_time") or ""),
            reproduced=reproduced,
            fidelity_label=label or "",
            fidelity_score=None if score is None else float(score),
        ))

    # Keep only the `limit` most-recent runs (by run root start_time).
    runs_newest_first = sorted(
        {a.run_id for a in attempts},
        key=lambda r: run_start.get(r, ""),
        reverse=True,
    )
    keep = set(runs_newest_first[:limit])
    return [a for a in attempts if a.run_id in keep]


def _ax_binary() -> str:
    """Resolve the `ax` CLI: same dir as the running interpreter, else PATH."""
    candidate = os.path.join(os.path.dirname(sys.executable), "ax")
    return candidate if os.path.exists(candidate) else "ax"


def fetch_prior_run_history(cfg, *, issue_url: str, limit: int = 5) -> list[PriorAttempt]:
    """Live AX fetch via the `ax` CLI, then parse.

    Exports the run-root + repro_attempt spans for the project and filters by
    issue in `parse_prior_attempts`. May raise (CLI missing, auth, network) — the
    seam's caller (load_learned_context) guards it into the inner loop.

    NB: a name/attribute filter without `--start-time` uses the time-series index,
    which lags ~6-12h, so very recent runs may not appear yet. That is acceptable
    for "prior-run" memory (prior runs are older); fresh same-session runs are not
    expected to be queryable immediately.
    """
    project = getattr(cfg, "arize_project_name", PROJECT_NAME)
    space = cfg.arize_space_id
    env = dict(os.environ)
    env["ARIZE_SPACE"] = space
    cmd = [
        _ax_binary(), "spans", "export", project,
        "--space", space,
        "--filter", f"name IN ('{RUN_ROOT_SPAN_NAME}', '{REPRO_ATTEMPT_SPAN_NAME}')",
        "--stdout", "-l", str(max(limit * 4, 50)),
    ]
    proc = subprocess.run(
        cmd, capture_output=True, text=True, timeout=_AX_QUERY_TIMEOUT_S, env=env,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"ax spans export failed: {proc.stderr.strip()[:200]}")
    spans = json.loads(proc.stdout or "[]")
    if not isinstance(spans, list):
        spans = spans.get("spans", []) if isinstance(spans, dict) else []
    return parse_prior_attempts(spans, issue_url=issue_url, limit=limit)
