"""Phoenix tracer registration — idempotent, env-driven, injectable for tests."""
from __future__ import annotations

import os

from opentelemetry import trace

_PROJECT_NAME = "triage-bug-repro"
_registered = False


def setup_tracing(cfg, *, _register=None):
    """Register the Phoenix tracer once and return a tracer named 'triage'.

    Sets PHOENIX_API_KEY / PHOENIX_COLLECTOR_ENDPOINT from cfg before registering.
    `_register` is injected in tests; defaults to phoenix.otel.register.
    """
    global _registered
    os.environ["PHOENIX_API_KEY"] = cfg.phoenix_api_key
    os.environ["PHOENIX_COLLECTOR_ENDPOINT"] = cfg.phoenix_collector_endpoint

    if not _registered:
        register = _register
        if register is None:
            from phoenix.otel import register as register  # noqa: PLC0414
        register(project_name=_PROJECT_NAME, auto_instrument=True)
        _registered = True

    return trace.get_tracer("triage")
