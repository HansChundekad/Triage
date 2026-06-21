import os

import triage.tracing.setup as setup_mod
from triage.tracing.setup import setup_tracing


class _AxCfg:
    trace_backend = "ax"
    arize_api_key = "ak-test"
    arize_space_id = "space-test"
    arize_project_name = "triage-bug-repro"
    # phoenix fields present but unused on the ax path
    phoenix_api_key = "pk-unused"
    phoenix_collector_endpoint = "https://app.phoenix.arize.com"


class _PhoenixCfg:
    trace_backend = "phoenix"
    arize_api_key = ""
    arize_space_id = ""
    arize_project_name = "triage-bug-repro"
    phoenix_api_key = "pk-test"
    phoenix_collector_endpoint = "https://app.phoenix.arize.com/s/space"


def _reset_registered():
    setup_mod._registered = False


def test_ax_backend_registers_arize_tracer(monkeypatch):
    _reset_registered()
    calls = []

    def fake_register(**kwargs):
        calls.append(kwargs)
        return object()

    tracer = setup_tracing(_AxCfg(), _register=fake_register)
    assert calls == [{
        "space_id": "space-test",
        "api_key": "ak-test",
        "project_name": "triage-bug-repro",
        "auto_instrument": True,
        "batch": False,
    }]
    # idempotent: second call does NOT register again
    setup_tracing(_AxCfg(), _register=fake_register)
    assert len(calls) == 1
    assert hasattr(tracer, "start_as_current_span")


def test_phoenix_backend_registers_phoenix_tracer_and_sets_env(monkeypatch):
    _reset_registered()
    monkeypatch.delenv("PHOENIX_API_KEY", raising=False)
    monkeypatch.delenv("PHOENIX_COLLECTOR_ENDPOINT", raising=False)
    calls = []

    def fake_register(**kwargs):
        calls.append(kwargs)
        return object()

    tracer = setup_tracing(_PhoenixCfg(), _register=fake_register)
    assert calls == [{"project_name": "triage-bug-repro", "auto_instrument": True}]
    assert os.environ["PHOENIX_API_KEY"] == "pk-test"
    assert os.environ["PHOENIX_COLLECTOR_ENDPOINT"] == "https://app.phoenix.arize.com/s/space"
    assert hasattr(tracer, "start_as_current_span")
