"""Task 6: Parser/Hypothesis Claude calls are wrapped in run-trace spans.

Asserts that when a real RunTrace is threaded into the agent callbacks, the
Claude reasoning call emits a named span (parser_extract_steps /
hypothesis_generation). With run_trace=None (default NullRunTrace) the callbacks
still run, no span is emitted — the no-op path that keeps the existing suites
unchanged.
"""
from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import triage.hypothesis_agent.agent as hyp_mod
from triage.hypothesis_agent.agent import make_diagnosis_callback
from triage.hypothesis_agent.reasoning import Diagnosis
from triage.parser_agent.agent import make_on_message
from triage.parser_agent.github import Issue
from triage.tracing.run_context import RunTrace
from tests._tracing_helpers import tracer_and_exporter

REPRO_ID = "repro-agent-id-123"


class _FakeAgent:
    name = "ParserAgent"

    def __init__(self) -> None:
        self.sent: list[tuple[list[str], str]] = []
        self.events: list[tuple[str, str]] = []

    async def send_message(self, mentions, text) -> None:
        self.sent.append((list(mentions), text))

    async def send_event(self, content, event_type, metadata=None) -> None:
        self.events.append((content, event_type))


def _payload(content="verdict: BUG REPRODUCED"):
    return SimpleNamespace(sender_id=REPRO_ID, sender_name="ReproAgent", content=content)


# --- hypothesis path -----------------------------------------------------

def test_diagnose_call_is_wrapped_in_span(monkeypatch):
    monkeypatch.setattr(
        hyp_mod,
        "diagnose",
        lambda evidence, client, model=None: Diagnosis(
            decision="confirm", root_cause="items[0] deref", redirect_instruction=""
        ),
    )
    tracer, exporter = tracer_and_exporter()

    async def go():
        with RunTrace(tracer) as run:
            cb = make_diagnosis_callback(
                client=object(), repro_agent_id=REPRO_ID, run_trace=run
            )
            await cb(_payload(), _FakeAgent())

    asyncio.run(go())
    names = [s.name for s in exporter.get_finished_spans()]
    assert "hypothesis_generation" in names


def test_diagnose_default_run_trace_emits_no_span(monkeypatch):
    monkeypatch.setattr(
        hyp_mod,
        "diagnose",
        lambda evidence, client, model=None: Diagnosis(
            decision="confirm", root_cause="x", redirect_instruction=""
        ),
    )
    tracer, exporter = tracer_and_exporter()
    # No run_trace passed -> NullRunTrace no-op.
    cb = make_diagnosis_callback(client=object(), repro_agent_id=REPRO_ID)
    asyncio.run(cb(_payload(), _FakeAgent()))
    assert "hypothesis_generation" not in [s.name for s in exporter.get_finished_spans()]


# --- parser path ---------------------------------------------------------

class _FakeMessages:
    def __init__(self, steps: list[str]) -> None:
        self._text = json.dumps({"steps": steps})

    async def create(self, **kwargs):
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=self._text)])


class _FakeAnthropic:
    def __init__(self, steps: list[str]) -> None:
        self.messages = _FakeMessages(steps)


def _fake_cfg() -> SimpleNamespace:
    return SimpleNamespace(
        band_parser=SimpleNamespace(agent_id="parser-id"),
        band_repro=SimpleNamespace(agent_id="repro-id"),
        band_hypothesis=SimpleNamespace(agent_id="hypothesis-id"),
        github_issue_url="https://github.com/o/r/issues/7",
    )


def test_extract_steps_call_is_wrapped_in_span():
    cfg = _fake_cfg()
    agent = _FakeAgent()
    anthropic_client = _FakeAnthropic(["Add a task"])
    issue_cache = {"issue": Issue(title="T", body="B", url="https://github.com/o/r/issues/7")}
    tracer, exporter = tracer_and_exporter()

    async def go():
        with RunTrace(tracer) as run:
            cb = make_on_message(
                cfg,
                anthropic_client=anthropic_client,
                http_client=object(),
                issue_cache=issue_cache,
                run_trace=run,
            )
            await cb(
                SimpleNamespace(
                    sender_id="repro-id",
                    sender_name="ReproAgent",
                    content="@ParserAgent step 3 found no Add button",
                ),
                agent,
            )

    asyncio.run(go())
    assert "parser_extract_steps" in [s.name for s in exporter.get_finished_spans()]
