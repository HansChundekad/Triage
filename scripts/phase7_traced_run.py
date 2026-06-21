#!/usr/bin/env python
"""Phase 7 traced run — the real Phase-6 retry loop under one Arize root span.

Single-process by design (§3 of the design spec): all three real callbacks share
one RunTrace root context, so the trace tree nests across async Band callbacks.
Mirrors scripts/phase6_live_run.py; --force-retry drives a real fail->succeed.
"""
from __future__ import annotations

import asyncio
import sys
import time

import anthropic
import httpx
from dotenv import load_dotenv

load_dotenv()

from triage.config import load_config
from triage.hypothesis_agent.agent import make_diagnosis_callback
from triage.parser_agent.agent import format_steps_message, make_on_message, post_initial_steps
from triage.parser_agent.github import fetch_issue
from triage.repro_agent.echo import make_repro_callback
from triage.repro_agent.loop import ReproLoopState
from triage.shared.band import BandAgent, ReproStepsPayload
from triage.tracing.setup import setup_tracing
from triage.tracing.run_context import RunTrace
from triage.tracing.artifacts import RunArtifacts

WALL_CLOCK_TIMEOUT = 600
STABILISE = 2.0
_FORCED_BROKEN_STEPS = [
    "Click the Delete button on the first task in the list",
    "Click the 'Yes, delete' confirmation button to confirm the deletion",
    "Click the Delete button on the next remaining task in the list",
    "Click the 'Yes, delete' confirmation button to confirm the deletion",
]


async def main(force_retry: bool = False) -> int:
    cfg = load_config()
    tracer = setup_tracing(cfg)

    parser_anthropic = anthropic.AsyncAnthropic(api_key=cfg.anthropic_api_key)
    hypothesis_anthropic = anthropic.Anthropic(api_key=cfg.anthropic_api_key)
    http_client = httpx.AsyncClient()
    issue_cache: dict = {"issue": None}
    repro_state = ReproLoopState()

    # Everything that touches spans happens INSIDE the open root: connect, the
    # run loop, AND disconnect, so child spans attach while triage_run is live.
    with RunTrace(tracer, issue_url=cfg.github_issue_url, app_url=cfg.app_url) as run:
        artifacts = RunArtifacts("./.triage_runs")
        print(f"[phase7] run dir: {artifacts.run_dir}")

        repro = BandAgent(
            name="ReproAgent",
            agent_id=cfg.band_repro.agent_id,
            api_key=cfg.band_repro.api_key,
            on_message=make_repro_callback(cfg, repro_state, run_trace=run, artifacts=artifacts),
        )
        parser = BandAgent(
            name="ParserAgent",
            agent_id=cfg.band_parser.agent_id,
            api_key=cfg.band_parser.api_key,
            on_message=make_on_message(
                cfg,
                anthropic_client=parser_anthropic,
                http_client=http_client,
                issue_cache=issue_cache,
                run_trace=run,
            ),
        )
        hypothesis = BandAgent(
            name="HypothesisAgent",
            agent_id=cfg.band_hypothesis.agent_id,
            api_key=cfg.band_hypothesis.api_key,
            on_message=make_diagnosis_callback(
                hypothesis_anthropic,
                cfg.band_repro.agent_id,
                run_trace=run,
            ),
        )

        room_id = await repro.connect(room_id=cfg.band_room_id)
        if cfg.band_room_id is None:
            await repro.add_participant("ParserAgent")
            await repro.add_participant("HypothesisAgent")
        await parser.connect(room_id=room_id)
        await hypothesis.connect(room_id=room_id)
        await asyncio.sleep(STABILISE)

        if force_retry:
            issue_cache["issue"] = await fetch_issue(cfg.github_issue_url, http_client=http_client)
            broken = ReproStepsPayload(issue_url=cfg.github_issue_url, steps=_FORCED_BROKEN_STEPS)
            await parser.send_message(["ReproAgent"], format_steps_message(broken))
        else:
            await post_initial_steps(
                cfg,
                anthropic_client=parser_anthropic,
                http_client=http_client,
                agent=parser,
                issue_cache=issue_cache,
                run_trace=run,
            )

        deadline = time.monotonic() + WALL_CLOCK_TIMEOUT
        while not repro_state.terminal and time.monotonic() < deadline:
            await asyncio.sleep(1)

        # --- 7B inline evaluator (runs while the root span is still open so the
        # annotations attach to live repro_attempt spans). Eval must NEVER wedge
        # the demo, so it is fully guarded. ---
        scored = None
        try:
            from triage.eval.run_eval import run_eval

            scored = run_eval(cfg, repro_state, artifacts, hypothesis_root_cause="")
            if scored.empty:
                print("[phase7] eval: no attempts to score")
            else:
                print("[phase7] eval scored attempts:")
                print(scored[["attempt_number", "repro_fidelity_label", "root_cause_label"]])
        except Exception as exc:  # noqa: BLE001 — eval must never wedge the demo
            print(f"[phase7] eval step failed (non-fatal): {exc}")

        # --- 7C synthesis: artifacts -> Claude -> report.json (frontend contract).
        # Inside the open root span so the `synthesis` span nests; fully guarded so
        # synthesis can NEVER wedge the demo. ---
        try:
            from triage.synthesis.synthesize import synthesize_run

            issue = issue_cache.get("issue")
            issue_dict = {
                "url": cfg.github_issue_url,
                "title": getattr(issue, "title", ""),
                "summary": (getattr(issue, "body", "") or "")[:280],
            }
            eval_scores = None
            if scored is not None and not scored.empty:
                last = scored.iloc[-1]
                fid, rc = last["repro_fidelity_score"], last["root_cause_score"]
                # Tolerate a missing per-row score (judge failure): keep what we have
                # so the report still writes rather than dropping on float(None).
                eval_scores = {
                    "repro_fidelity": float(fid) if fid is not None else None,
                    "root_cause_correctness": float(rc) if rc is not None else None,
                }
            report_path = synthesize_run(
                cfg, artifacts, client=hypothesis_anthropic, issue=issue_dict,
                hypothesis_root_cause="", eval_scores=eval_scores, run_trace=run)
            print(f"[phase7] report written: {report_path}")
        except Exception as exc:  # noqa: BLE001 — synthesis must never wedge the demo
            print(f"[phase7] synthesis step failed (non-fatal): {exc}")

        print("\n=== RUN SUMMARY ===")
        print(f"terminal: {repro_state.terminal}  attempts: {repro_state.attempts}/{repro_state.max_attempts}")
        for i, url in enumerate(repro_state.session_urls, 1):
            print(f"  attempt {i}: {url}")

        await parser.disconnect()
        await hypothesis.disconnect()
        await repro.disconnect()
        await http_client.aclose()
        return 0 if repro_state.terminal else 1


if __name__ == "__main__":
    force = "--force-retry" in sys.argv[1:]
    try:
        sys.exit(asyncio.run(main(force_retry=force)))
    except KeyboardInterrupt:
        print("\n[phase7_traced_run] interrupted.")
        sys.exit(0)
