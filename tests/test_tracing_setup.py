import os
from triage.tracing.setup import setup_tracing


class _Cfg:
    phoenix_api_key = "pk-test"
    phoenix_collector_endpoint = "https://app.phoenix.arize.com"


def test_setup_tracing_registers_once_and_sets_env():
    calls = []

    def fake_register(**kwargs):
        calls.append(kwargs)
        return object()

    tracer = setup_tracing(_Cfg(), _register=fake_register)
    # called once with the project name + auto_instrument
    assert calls == [{"project_name": "triage-bug-repro", "auto_instrument": True}]
    assert os.environ["PHOENIX_API_KEY"] == "pk-test"
    assert os.environ["PHOENIX_COLLECTOR_ENDPOINT"] == "https://app.phoenix.arize.com"
    # idempotent: second call does NOT register again
    setup_tracing(_Cfg(), _register=fake_register)
    assert len(calls) == 1
    # returns something usable as a tracer (has start_as_current_span)
    assert hasattr(tracer, "start_as_current_span")
