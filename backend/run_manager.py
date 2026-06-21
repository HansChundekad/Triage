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
outbound message so _build_report can use the real last hypothesis text instead
of an invented string.
"""
from __future__ import annotations

import asyncio
import time
import uuid
from typing import AsyncIterator

import anthropic
import httpx

from triage.config import load_config
from triage.hypothesis_agent.agent import make_diagnosis_callback
from triage.parser_agent.agent import make_on_message, post_initial_steps
from triage.parser_agent.github import fetch_issue  # noqa: F401  (parity w/ harness)
from triage.repro_agent.echo import make_repro_callback
from triage.repro_agent.loop import ReproLoopState, is_confirm
from triage.shared.band import BandAgent

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
      run.last_hypothesis_text so _build_report can surface a real hypothesis.
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
        used as rootCause.hypothesis in the report.
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


class RunRegistry:
    def __init__(self) -> None:
        self._runs: dict[str, _Run] = {}

    def create(self, issue_url: str) -> str:
        run_id = uuid.uuid4().hex[:12]
        run = _Run(run_id, issue_url)
        self._runs[run_id] = run
        asyncio.create_task(self._drive(run))
        return run_id

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

            repro = BandAgent("ReproAgent", cfg.band_repro.agent_id, cfg.band_repro.api_key,
                              on_message=make_repro_callback(cfg, state))
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

            await post_initial_steps(cfg, anthropic_client=parser_anthropic,
                                     http_client=http_client, agent=parser, issue_cache=issue_cache)

            deadline = time.monotonic() + WALL_CLOCK_TIMEOUT
            while not state.terminal and time.monotonic() < deadline:
                await asyncio.sleep(1)

            report = _build_report(run)
            await run.emit("report", report)

            for a in (parser, hypothesis, repro):
                await a.disconnect()
            await http_client.aclose()
        except Exception as exc:  # honest terminal error — never hang
            await run.emit("error", {"message": f"{type(exc).__name__}: {exc}"})
        finally:
            run.done = True


def _build_report(run: _Run) -> dict:
    """Synthesize the RunReport from the run's observed signals (spec §6).

    Uses run.reproduced (set by _tap from the live HypothesisAgent confirm
    message — not from ReproLoopState which cannot distinguish success from
    gave-up) and run.last_hypothesis_text for rootCause.hypothesis.

    PLACEHOLDER — reconcile to the Arize worktree's synthesis output.  Per-step
    screenshots are not surfaced by ReproResultPayload, so steps are text-only
    here and the card leans on the session replay links.
    """
    # Gather session URLs from the tapped buffer (step events that carried
    # session_url, plus the state we do NOT have direct access to here).
    # Pull them from the buffer: normalize_event stores session_url on the dict.
    session_urls: list[str] = []
    for _name, data in run.buffer:
        if data.get("type") == "step" and data.get("session_url"):
            url = data["session_url"]
            if url not in session_urls:
                session_urls.append(url)

    reproduced = run.reproduced
    attempts = [{"n": i + 1,
                 "outcome": "reproduced" if (reproduced and i == len(session_urls) - 1) else "fail",
                 "sessionId": u.rstrip("/").split("/")[-1], "replayUrl": u}
                for i, u in enumerate(session_urls)]

    hypothesis_text = run.last_hypothesis_text or "see transcript"

    return {
        "issueUrl": run.issue_url,
        "status": "reproduced" if reproduced else "not_reproduced",
        "verdict": "Bug reproduced." if reproduced else "Could not reproduce.",
        "reproSteps": [],
        "rootCause": {"hypothesis": hypothesis_text,
                      "evidence": "", "confidence": "medium"},
        "attempts": attempts,
        "consoleErrors": [],
    }
