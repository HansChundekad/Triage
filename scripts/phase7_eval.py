#!/usr/bin/env python
"""Phase 7B standalone re-scorer.

Re-runs `run_eval` over an EXISTING run directory without spinning a fresh browser
run. Use it to (re)score attempts after a live run, or to iterate on the judges
against captured evidence.

NOTE (Phoenix→AX migration): the in-loop eval write attaches to live AX spans via
in-process span-ids (see triage.tracing.run_context). This standalone re-scorer has
no live spans, so it recomputes scores but cannot re-attach them to AX — the eval
*write* requires the harness path (scripts/phase7_traced_run.py). The judge scores
it prints are still authoritative for inspecting/iterating on the judges.

Usage:
    .venv/bin/python scripts/phase7_eval.py <run_dir> [--root-cause "..."]

<run_dir> is a directory containing an `attempts.json` (a per-run dir created by
RunArtifacts, e.g. ./.triage_runs/20260620T...). If omitted, the most recent run
dir under ./.triage_runs is used.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from triage.config import load_config
from triage.eval.run_eval import run_eval

_RUNS_ROOT = "./.triage_runs"


class _ExistingRunArtifacts:
    """Read-only view over an existing run dir's attempts.json (no new dir)."""

    def __init__(self, run_dir: str | Path):
        self._dir = Path(run_dir)
        self._attempts_path = self._dir / "attempts.json"

    @property
    def run_dir(self) -> str:
        return str(self._dir)

    def load_attempts(self) -> list[dict]:
        if not self._attempts_path.exists():
            return []
        return json.loads(self._attempts_path.read_text())


def _latest_run_dir() -> Path | None:
    root = Path(_RUNS_ROOT)
    if not root.is_dir():
        return None
    candidates = [p for p in root.iterdir() if p.is_dir() and (p / "attempts.json").exists()]
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.name)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Re-score a prior TRIAGE run.")
    parser.add_argument("run_dir", nargs="?", help="run dir containing attempts.json")
    parser.add_argument("--root-cause", default="", help="hypothesis root cause text")
    args = parser.parse_args(argv)

    run_dir = Path(args.run_dir) if args.run_dir else _latest_run_dir()
    if run_dir is None:
        print(f"[phase7_eval] no run dir found under {_RUNS_ROOT}", file=sys.stderr)
        return 2
    if not (run_dir / "attempts.json").exists():
        print(f"[phase7_eval] no attempts.json in {run_dir}", file=sys.stderr)
        return 2

    cfg = load_config()
    artifacts = _ExistingRunArtifacts(run_dir)
    print(f"[phase7_eval] re-scoring {run_dir}")

    scored = run_eval(cfg, repro_state=None, artifacts=artifacts,
                      hypothesis_root_cause=args.root_cause)
    if scored.empty:
        print("[phase7_eval] no attempts to score")
        return 0
    print(scored[["attempt_number", "repro_fidelity_label", "repro_fidelity_score",
                  "root_cause_label", "honesty_label"]])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
