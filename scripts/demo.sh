#!/usr/bin/env bash
# TRIAGE demo — the ONE command to run the full forced fail→succeed end to end.
#
#   ./scripts/demo.sh
#
# Deterministic & repeatable: ParserAgent posts deliberately-incomplete steps so
# attempt 1 always FAILS, HypothesisAgent redirect_parsers, ParserAgent re-parses,
# a FRESH Browserbase session runs attempt 2, which SUCCEEDS, then eval + report.
#
# Watch three live surfaces (the run prints exactly where):
#   1) Browserbase live view  — a URL prints at each attempt start
#   2) Band transcript        — streams live in this console (💬 lines)
#   3) Arize AX trace         — trace_id prints at the end; open the newest triage_run
set -euo pipefail

cd "$(dirname "$0")/.."

# Determinism: the outer-loop memory path (TRIAGE_OUTER_LOOP=1) would re-route the
# first attempt through prior-run memory instead of the forced broken steps. Force
# it OFF here so the demo produces the identical fail→succeed every single run.
export TRIAGE_OUTER_LOOP=0

exec .venv/bin/python scripts/phase7_traced_run.py --force-retry
