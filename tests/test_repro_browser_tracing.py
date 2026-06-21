import asyncio
import base64
import types

import pytest

import triage.repro_agent.browser as browser
from triage.tracing.run_context import RunTrace
from tests._tracing_helpers import tracer_and_exporter


class _Cfg:
    browserbase_api_key = "bb"
    anthropic_api_key = "an"
    app_url = "http://app.test"


def _fake_stagehand_and_playwright(monkeypatch, body_text, console_text):
    """Patch AsyncStagehand + async_playwright with minimal async fakes."""
    png = base64.b64encode(b"PNG").decode()

    class _Result:
        def __init__(self, **kw): self.__dict__.update(kw)

    class _Data:
        def __init__(self, result): self.data = types.SimpleNamespace(result=result)

    class _Session:
        id = "sess-123"
        data = types.SimpleNamespace(cdp_url="ws://cdp")
        async def navigate(self, url): return None
        async def observe(self, instruction): return _Data([{"e": 1}])
        async def act(self, input):
            return _Data(_Result(success=True, message="clicked"))
        async def extract(self, instruction, schema):
            return _Data({"body_text": body_text})
        async def end(self): return None

    class _Sessions:
        async def start(self, **kw): return _Session()

    class _Client:
        sessions = _Sessions()
        async def close(self): return None

    class _Page:
        def on(self, event, cb):
            if event == "console" and console_text:
                cb(types.SimpleNamespace(type="error", text=console_text))
        async def screenshot(self): return b"PNG"

    class _Ctx: pages = [_Page()]
    class _Browser:
        contexts = [_Ctx()]
        async def close(self): return None
    class _Chromium:
        async def connect_over_cdp(self, url): return _Browser()
    class _PW:
        chromium = _Chromium()
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return None

    monkeypatch.setattr(browser, "AsyncStagehand", lambda **kw: _Client(), raising=False)
    monkeypatch.setattr(browser, "async_playwright", lambda: _PW(), raising=False)
    # browser.py imports these names *inside* run_repro; patch the source modules:
    import stagehand, playwright.async_api as pw_api
    monkeypatch.setattr(stagehand, "AsyncStagehand", lambda **kw: _Client())
    monkeypatch.setattr(pw_api, "async_playwright", lambda: _PW())
    return png


def test_run_repro_emits_one_stagehand_span_per_step(monkeypatch):
    _fake_stagehand_and_playwright(
        monkeypatch, body_text="", console_text="Cannot read properties of undefined")
    tracer, exporter = tracer_and_exporter()

    async def go():
        with RunTrace(tracer) as run:
            with run.attempt_span(1) as attempt:
                with run.child_span("browser_execution", attempt) as be:
                    return await browser.run_repro(
                        _Cfg(), ["click delete", "confirm delete"],
                        run_trace=run, attempt=1, browser_execution_span=be)

    result = asyncio.run(go())
    assert result.success is True  # blank body + matching console error
    steps = [s for s in exporter.get_finished_spans() if s.name == "stagehand_action"]
    assert len(steps) == 2
    assert steps[0].attributes["step.index"] == 1
    assert steps[0].attributes["action.success"] is True
    assert "Cannot read properties of undefined" in steps[1].attributes["console.error"]
