import asyncio
import types

import triage.repro_agent.echo as echo
from triage.repro_agent.loop import ReproLoopState
from triage.shared.band import ReproResultPayload
from triage.tracing.run_context import RunTrace
from triage.tracing.artifacts import RunArtifacts
from tests._tracing_helpers import tracer_and_exporter


class _Ids:
    agent_id = "x"


class _Cfg:
    band_parser = _Ids(); band_hypothesis = _Ids(); app_url = "http://app"
    github_issue_url = "http://issue"


class _Agent:
    def __init__(self): self.events = []; self.messages = []
    async def send_event(self, *a, **k): self.events.append(a)
    async def send_message(self, recipients, text): self.messages.append((recipients, text))


def test_run_attempt_emits_repro_attempt_span_with_honest_flag(monkeypatch, tmp_path):
    async def fake_run_repro(cfg, steps, tweak=None, **kw):
        return ReproResultPayload(success=True, evidence=["e"],
                                  console_errors=["Cannot read..."],
                                  session_url="https://www.browserbase.com/sessions/abc")
    monkeypatch.setattr(echo, "run_repro", fake_run_repro)

    tracer, exporter = tracer_and_exporter()
    art = RunArtifacts(tmp_path)
    state = ReproLoopState(); state.steps = ["click delete"]; state.attempts = 0

    async def go():
        with RunTrace(tracer) as run:
            await echo._run_attempt(_Cfg(), state, _Agent(), tweak=None,
                                    run_trace=run, artifacts=art)

    asyncio.run(go())
    spans = {s.name: s for s in exporter.get_finished_spans()}
    assert "repro_attempt" in spans
    assert spans["repro_attempt"].attributes["bug.detected"] is True
    assert spans["repro_attempt"].attributes["attempt.number"] == 1
    assert "browserbase.session_url" in spans["repro_attempt"].attributes
    assert art.load_attempts()[0]["bug_detected"] is True
