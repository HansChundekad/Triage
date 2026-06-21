"""Run artifacts -> Claude structured output -> validated ReproReport.

Mirrors triage/parser_agent/claude.py for the Claude call shape (output_config
json_schema + adaptive thinking) — the verified-working pattern in this repo.
Claude generates only the observed fields (CLAUDE_OUTPUT_SCHEMA); the server fills
session replay URLs, eval scores, and the timestamp in assemble_report.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from triage.synthesis.schema import (
    Attempt, EvalScores, Evidence, Issue, ReproReport, RootCause, ReproStep,
    CLAUDE_OUTPUT_SCHEMA, validate_report,
)

_MODEL = "claude-sonnet-4-6"
_MAX_TOKENS = 4096
_SYSTEM = (
    "You are a senior engineer writing a concise, accurate bug-reproduction report "
    "from the evidence a browser-automation agent captured. Use ONLY the provided "
    "evidence; do not invent steps, errors, or causes. Mark a step 'crash' when the "
    "evidence shows the page broke on that step, 'fail' if the action did not work, "
    "else 'ok'. Set verdict 'reproduced' only if the reported bug clearly fired."
)


def build_synthesis_prompt(issue: dict, attempts: list[dict], hypothesis_root_cause: str) -> str:
    """Render the user-turn prompt from the issue + per-attempt artifacts (pure)."""
    final = attempts[-1] if attempts else {}
    lines = [
        f"Issue title: {issue['title']}",
        f"Issue summary: {issue['summary']}",
        "",
        "Confirmed repro steps (final attempt):",
        *[f"  - {s}" for s in final.get("steps", [])],
        "",
        "Per-attempt evidence:",
    ]
    for a in attempts:
        lines.append(f"  attempt {a['attempt']} (bug_detected={a.get('bug_detected')}):")
        lines += [f"    - {e}" for e in a.get("evidence", [])]
        lines += [f"    console: {c}" for c in a.get("console_errors", [])]
    lines += ["", f"Diagnosed root cause (from HypothesisAgent): {hypothesis_root_cause}",
              "", "Produce the structured report."]
    return "\n".join(lines)


def assemble_report(model_output: dict, *, issue: dict, attempts: list[dict],
                    eval_scores: dict | None, now: str) -> ReproReport:
    """Merge Claude's generated fields with server-filled fields, then validate (pure)."""
    report = ReproReport(
        issue=Issue(**issue),
        verdict=model_output["verdict"],
        repro_steps=[ReproStep(**s) for s in model_output["repro_steps"]],
        root_cause=RootCause(**model_output["root_cause"]),
        evidence=Evidence(**model_output["evidence"]),
        # Number attempts sequentially in capture order: a redirect resets the
        # loop's counter, so the recorded "attempt" values can repeat (e.g. 1, 1).
        attempts=[Attempt(number=i, session_replay_url=a.get("session_url", ""),
                          bug_detected=bool(a.get("bug_detected")))
                  for i, a in enumerate(attempts, start=1)],
        eval_scores=EvalScores(**eval_scores) if eval_scores else None,
        generated_at=now,
    )
    validate_report(report.to_dict())
    return report


def synthesize_run(cfg, artifacts, *, client, issue: dict, hypothesis_root_cause: str,
                   eval_scores: dict | None = None, run_trace=None) -> str:
    """Synthesize a run's artifacts into report.json via Claude. Returns the path.

    `client` is an anthropic.Anthropic-shaped client (sync messages.create), injected
    for testability. `run_trace`, when a real RunTrace, wraps the call in a `synthesis`
    span; defaults to a no-op.
    """
    from triage.tracing.run_context import NullRunTrace
    run_trace = run_trace if run_trace is not None else NullRunTrace()

    attempts = artifacts.load_attempts()
    prompt = build_synthesis_prompt(issue, attempts, hypothesis_root_cause)

    with run_trace.claude_span("synthesis"):
        response = client.messages.create(
            model=_MODEL, max_tokens=_MAX_TOKENS,
            thinking={"type": "adaptive"}, system=_SYSTEM,
            output_config={"format": {"type": "json_schema", "schema": CLAUDE_OUTPUT_SCHEMA}},
            messages=[{"role": "user", "content": prompt}],
        )
    text = next(b.text for b in response.content if getattr(b, "type", None) == "text")
    model_output = json.loads(text)

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    report = assemble_report(model_output, issue=issue, attempts=attempts,
                             eval_scores=eval_scores, now=now)
    return artifacts.write_report(report.to_dict())
