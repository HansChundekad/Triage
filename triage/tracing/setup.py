"""Tracer registration — idempotent, env-driven, injectable for tests.

Primary backend is **Arize AX** (`arize.otel.register` → otlp.arize.com); the
open-source Phoenix path is kept as a fallback, selected by `cfg.trace_backend`.
Both write OpenInference spans — the span structure is backend-agnostic.
"""
from __future__ import annotations

import os

from opentelemetry import trace

_PROJECT_NAME = "triage-bug-repro"
_registered = False


def setup_tracing(cfg, *, _register=None):
    """Register the trace backend once and return a tracer named 'triage'.

    Selects the backend from ``cfg.trace_backend`` ("ax" default, "phoenix"
    fallback). ``_register`` is injected in tests; otherwise it defaults to the
    selected backend's register function. Idempotent across calls.
    """
    global _registered
    backend = getattr(cfg, "trace_backend", "ax")

    if not _registered:
        if backend == "phoenix":
            # Fallback: open-source Phoenix Cloud. Auth via PHOENIX_* env vars.
            os.environ["PHOENIX_API_KEY"] = cfg.phoenix_api_key
            os.environ["PHOENIX_COLLECTOR_ENDPOINT"] = cfg.phoenix_collector_endpoint
            register = _register
            if register is None:
                from phoenix.otel import register as register  # noqa: PLC0414
            register(project_name=_PROJECT_NAME, auto_instrument=True)
        else:
            # Primary: Arize AX. Creds ride as OTLP headers to otlp.arize.com;
            # batch=False → SimpleSpanProcessor (immediate export, no exit-flush
            # needed) to mirror Phoenix's behaviour for the short-lived scripts.
            register = _register
            if register is None:
                from arize.otel import register as register  # noqa: PLC0414
            register(
                space_id=cfg.arize_space_id,
                api_key=cfg.arize_api_key,
                project_name=getattr(cfg, "arize_project_name", _PROJECT_NAME),
                auto_instrument=True,
                batch=False,
            )
        _registered = True

    return trace.get_tracer("triage")
