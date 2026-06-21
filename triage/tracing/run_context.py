"""RunTrace — a run-level root span that hands out explicitly-parented children.

Spans created inside separate async Band callbacks cannot rely on OTEL's implicit
current-span context to nest. RunTrace stores the root span's Context and parents
every child explicitly, producing one legible tree across callbacks.
"""
from __future__ import annotations

from contextlib import contextmanager

from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode


def set_span_ok(span, ok: bool) -> None:
    """Set OTEL status honestly from a boolean outcome (no-op if span is None)."""
    if span is None:
        return
    span.set_status(Status(StatusCode.OK if ok else StatusCode.ERROR))


class RunTrace:
    """Holds the root `triage_run` span and parents children under it explicitly."""

    def __init__(self, tracer, *, issue_url: str = "", app_url: str = ""):
        self._tracer = tracer
        self._issue_url = issue_url
        self._app_url = app_url
        self._root = None
        self._root_ctx = None

    def __enter__(self) -> "RunTrace":
        self._root = self._tracer.start_span("triage_run")
        if self._issue_url:
            self._root.set_attribute("github.issue_url", self._issue_url)
        if self._app_url:
            self._root.set_attribute("app.url", self._app_url)
        self._root_ctx = trace.set_span_in_context(self._root)
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if exc is not None:
            self._root.record_exception(exc)
            set_span_ok(self._root, False)
        self._root.end()

    @contextmanager
    def attempt_span(self, number: int):
        span = self._tracer.start_span("repro_attempt", context=self._root_ctx)
        span.set_attribute("attempt.number", number)
        try:
            yield span
        finally:
            span.end()

    @contextmanager
    def child_span(self, name: str, parent):
        ctx = trace.set_span_in_context(parent)
        span = self._tracer.start_span(name, context=ctx)
        try:
            yield span
        finally:
            span.end()

    @contextmanager
    def claude_span(self, name: str, *, attempt_number: int | None = None):
        span = self._tracer.start_span(name, context=self._root_ctx)
        if attempt_number is not None:
            span.set_attribute("attempt.number", attempt_number)
        try:
            yield span
        finally:
            span.end()


class NullRunTrace:
    """No-op RunTrace for the untraced/test path. Same interface."""

    def __enter__(self) -> "NullRunTrace":
        return self

    def __exit__(self, *a) -> None:
        return None

    @contextmanager
    def attempt_span(self, number: int):
        yield None

    @contextmanager
    def child_span(self, name: str, parent):
        yield None

    @contextmanager
    def claude_span(self, name: str, *, attempt_number: int | None = None):
        yield None
