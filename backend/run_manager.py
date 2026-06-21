"""Drive a live TRIAGE run and tap the Band transcript into a stream queue.

The three real agents are composed exactly as scripts/phase6_live_run.py does.
We never modify band.py: the tap wraps each BandAgent's bound send_message /
send_event at composition time, so every directed message and logged event is
mirrored into the run's asyncio.Queue as a normalized stream event (spec §5).

Honest reproduced signal
------------------------
ReproLoopState.terminal is set True in TWO places inside echo.py:
  (a) on kind == "confirm" — real success
  (b) when attempts_exhausted  — gave up / failure

The state object has NO confirmed/root_cause fields.  We therefore track
`_Run.reproduced` ourselves: the _tap wrapper on each agent detects when
HypothesisAgent sends a message to ReproAgent whose text matches is_confirm().
When that fires, run.reproduced is set True before the message is forwarded.
Likewise, `_Run.last_hypothesis_text` is updated on every HypothesisAgent
outbound message so the synthesised report can use the real last hypothesis text
(the diagnosed root cause) instead of an invented string.

Report contract
---------------
The report emitted at the end of a run is the canonical Arize ``ReproReport``
produced by ``triage.synthesis`` — the single source of truth. We never build a
bespoke shape here: ``build_report_dict`` runs the captured artifacts through
``synthesize_run`` (Claude) and returns exactly what it wrote to ``report.json``.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from pathlib import Path
from typing import AsyncIterator

import anthropic
import httpx

from triage.config import load_config
from triage.memory import load_learned_context
from triage.hypothesis_agent.agent import make_diagnosis_callback
from triage.parser_agent.agent import make_on_message, post_initial_steps
from triage.parser_agent.github import fetch_issue  # noqa: F401  (parity w/ harness)
from triage.repro_agent.echo import make_repro_callback
from triage.repro_agent.loop import ReproLoopState, is_confirm
from triage.shared.band import BandAgent
from triage.synthesis.synthesize import synthesize_run
from triage.tracing.artifacts import RunArtifacts

logger = logging.getLogger(__name__)

WALL_CLOCK_TIMEOUT = 600
_EVENT_KIND = {"task": "browser", "thought": "thought", "error": "error"}


def normalize_message(from_name: str, mentions: list[str], text: str) -> dict:
    return {"type": "message", "from": from_name, "to": list(mentions),
            "text": text, "ts": time.time()}


def normalize_event(agent: str, content: str, event_type: str, metadata: dict | None) -> dict:
    ev = {"type": "step", "agent": agent, "kind": _EVENT_KIND.get(event_type, "thought"),
          "text": content, "screenshot": None, "ts": time.time()}
    if metadata and metadata.get("session_url"):
        url = metadata["session_url"]
        ev["session_url"] = url
    return ev


def _tap(agent: BandAgent, run: "_Run") -> None:
    """Wrap bound send_message/send_event to mirror traffic into the run.

    Routes through `run.emit` so tapped traffic lands in both the live `queue`
    (for the SSE stream) and `buffer` (for the snapshot endpoint), exactly like
    the run's own status/report/error emits.

    Also derives the honest reproduced signal:
    - When HypothesisAgent sends a message to ReproAgent with is_confirm() text,
      set run.reproduced = True.
    - Every HypothesisAgent outbound message text is saved to
      run.last_hypothesis_text so synthesis can surface a real root cause.
    """
    orig_msg = agent.send_message
    orig_evt = agent.send_event

    async def send_message(mentions, text):
        await run.emit("message", normalize_message(agent.name, mentions, text))
        # Derive honest reproduced signal from the live message stream.
        if agent.name == "HypothesisAgent":
            run.last_hypothesis_text = text
            # Confirm marker in a HypothesisAgent→ReproAgent message = real success.
            if "ReproAgent" in (mentions or []) and is_confirm(text):
                run.reproduced = True
        return await orig_msg(mentions, text)

    async def send_event(content, event_type, metadata=None):
        await run.emit("step", normalize_event(agent.name, content, event_type, metadata))
        return await orig_evt(content, event_type, metadata)

    agent.send_message = send_message  # type: ignore[method-assign]
    agent.send_event = send_event      # type: ignore[method-assign]


class _Run:
    """One live run. Single SSE subscriber (the frontend opens exactly one
    EventSource right after POST). `queue` is the live tail the stream drains;
    `buffer` is a parallel history used only by the snapshot endpoint, so the
    two never double-emit.

    reproduced: set True by _tap when HypothesisAgent confirms success.
    last_hypothesis_text: most recent HypothesisAgent outbound message text,
        passed to synthesis as the diagnosed root cause for the report.
    """

    def __init__(self, run_id: str, issue_url: str) -> None:
        self.run_id = run_id
        self.issue_url = issue_url
        self.queue: asyncio.Queue = asyncio.Queue()
        self.buffer: list[tuple[str, dict]] = []
        self.done = False
        self.reproduced: bool = False
        self.last_hypothesis_text: str = ""

    async def emit(self, name: str, data: dict) -> None:
        self.buffer.append((name, data))
        await self.queue.put((name, data))


async def maybe_inject_learned_context(cfg, parser_agent) -> str | None:
    """Phase 7.5 (guarded): post prior-run memory into the room before steps.

    Returns the hint to pass into post_initial_steps(prior_context=...), or None.
    A single deletable block — the outer-loop cut-path.
    """
    hint = load_learned_context(cfg)
    if not hint:
        return None
    await parser_agent.send_message(
        ["ReproAgent", "HypothesisAgent"], f"🧠 Prior-run memory: {hint}")
    return hint


class RunRegistry:
    def __init__(self) -> None:
        self._runs: dict[str, _Run] = {}

    def create(self, issue_url: str) -> str:
        run_id = uuid.uuid4().hex[:12]
        run = _Run(run_id, issue_url)
        self._runs[run_id] = run
        asyncio.create_task(self._drive(run))
        return run_id

    def has(self, run_id: str) -> bool:
        return run_id in self._runs

    def snapshot(self, run_id: str) -> dict:
        run = self._runs[run_id]
        return {"runId": run_id, "done": run.done, "events": [d for _, d in run.buffer]}

    async def stream(self, run_id: str) -> AsyncIterator[tuple[str, dict]]:
        run = self._runs[run_id]
        while True:                              # drain the live tail only
            name, data = await run.queue.get()
            yield name, data
            if name in ("report", "error"):
                break

    async def _drive(self, run: _Run) -> None:
        try:
            cfg = load_config()
            parser_anthropic = anthropic.AsyncAnthropic(api_key=cfg.anthropic_api_key)
            hypothesis_anthropic = anthropic.Anthropic(api_key=cfg.anthropic_api_key)
            http_client = httpx.AsyncClient()
            issue_cache: dict = {"issue": None}
            state = ReproLoopState()
            artifacts = RunArtifacts("./.triage_runs")

            repro = BandAgent("ReproAgent", cfg.band_repro.agent_id, cfg.band_repro.api_key,
                              on_message=make_repro_callback(cfg, state, artifacts=artifacts))
            parser = BandAgent("ParserAgent", cfg.band_parser.agent_id, cfg.band_parser.api_key,
                               on_message=make_on_message(cfg, anthropic_client=parser_anthropic,
                                                          http_client=http_client, issue_cache=issue_cache))
            hypothesis = BandAgent("HypothesisAgent", cfg.band_hypothesis.agent_id,
                                   cfg.band_hypothesis.api_key,
                                   on_message=make_diagnosis_callback(hypothesis_anthropic,
                                                                      cfg.band_repro.agent_id))
            for a in (repro, parser, hypothesis):
                _tap(a, run)

            await run.emit("status", {"phase": "parsing", "attempt": 1,
                                      "maxAttempts": state.max_attempts})
            room_id = await repro.connect(room_id=cfg.band_room_id)
            if cfg.band_room_id is None:
                await repro.add_participant("ParserAgent")
                await repro.add_participant("HypothesisAgent")
            await parser.connect(room_id=room_id)
            await hypothesis.connect(room_id=room_id)
            await asyncio.sleep(2.0)

            prior_context = await maybe_inject_learned_context(cfg, parser)
            await post_initial_steps(cfg, anthropic_client=parser_anthropic,
                                     http_client=http_client, agent=parser,
                                     issue_cache=issue_cache, prior_context=prior_context)

            deadline = time.monotonic() + WALL_CLOCK_TIMEOUT
            while not state.terminal and time.monotonic() < deadline:
                await asyncio.sleep(1)

            # Synthesise the canonical ReproReport from the captured artifacts.
            # Off the event loop: synthesize_run + eval are blocking (Claude /
            # judges). Honest root cause = the real last HypothesisAgent message.
            issue_obj = issue_cache.get("issue")
            issue_dict = {
                "url": run.issue_url,
                "title": getattr(issue_obj, "title", "") or "",
                "summary": (getattr(issue_obj, "body", "") or "")[:280],
            }
            report = await asyncio.to_thread(
                build_report_dict, cfg, artifacts,
                client=hypothesis_anthropic, issue=issue_dict,
                hypothesis_root_cause=run.last_hypothesis_text,
            )
            await run.emit("report", report_event_data(report))

            for a in (parser, hypothesis, repro):
                await a.disconnect()
            await http_client.aclose()
        except Exception as exc:  # honest terminal error — never hang
            await run.emit("error", {"message": f"{type(exc).__name__}: {exc}"})
        finally:
            run.done = True


def _guarded_eval_scores(cfg, artifacts, hypothesis_root_cause: str) -> dict | None:
    """Final-attempt LLM-judge scores for the report, or None. Never raises.

    Decoupled from Arize AX span-logging: run_eval's eval write needs live spans,
    but the report only needs the scores. So we drive the proven pure path directly
    (build_eval_dataframe → score_attempts via the Anthropic judge).
    """
    try:
        from triage.eval.run_eval import build_eval_dataframe, score_attempts
        from triage.eval.judges import (
            build_judge_llm, make_fidelity_judge, make_root_cause_judge,
        )

        attempts = artifacts.load_attempts()
        if not attempts:
            return None
        df = build_eval_dataframe(attempts, cfg.github_issue_url, hypothesis_root_cause)
        llm = build_judge_llm(cfg)
        scored = score_attempts(
            df,
            fidelity_judge=make_fidelity_judge(llm),
            root_cause_judge=make_root_cause_judge(llm),
        )
        last = scored.iloc[-1]

        def _f(v):
            return float(v) if v is not None else None

        return {
            "repro_fidelity": _f(last["repro_fidelity_score"]),
            "root_cause_correctness": _f(last["root_cause_score"]),
        }
    except Exception as exc:  # noqa: BLE001 — eval must never wedge the report
        logger.warning("[run_manager] eval scoring skipped (non-fatal): %s", exc)
        return None


def build_report_dict(cfg, artifacts, *, client, issue: dict,
                      hypothesis_root_cause: str) -> dict:
    """Produce the canonical Arize ReproReport for a finished run.

    ``triage.synthesis`` is the single source of truth: this runs guarded eval
    scoring, then ``synthesize_run`` writes ``report.json`` (Claude generates the
    observed fields; the server fills replay URLs, eval scores and the timestamp).
    We load and return exactly that dict — no placeholder shape is built here.
    """
    eval_scores = _guarded_eval_scores(cfg, artifacts, hypothesis_root_cause)
    report_path = synthesize_run(
        cfg, artifacts, client=client, issue=issue,
        hypothesis_root_cause=hypothesis_root_cause, eval_scores=eval_scores,
    )
    return json.loads(Path(report_path).read_text())


def report_event_data(report: dict) -> dict:
    """SSE `data` for the report event: wraps the canonical ReproReport so the
    frontend's {type:"report", ...data} spread yields {type:"report", report:{…}}."""
    return {"report": report}
