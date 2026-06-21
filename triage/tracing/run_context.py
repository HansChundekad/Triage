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
        # {attempt_id: span_id_hex} captured in-process at span creation, so eval
        # logging can attach to the live AX spans without a (lagging) query-back.
        # Keyed on the RUN-UNIQUE attempt id (not attempt.number, which resets to 1
        # on every redirect_parser re-parse via ReproLoopState.reset and would
        # otherwise overwrite the prior attempt's span id).
        self.span_ids: dict[int, str] = {}
        self._attempt_seq = 0

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

    def new_attempt_id(self) -> int:
        """A run-unique, monotonic attempt id.

        Unlike ``attempt.number`` (reset to 1 on every redirect_parser re-parse via
        ``ReproLoopState.reset``), this never collides within a run, so each
        ``repro_attempt`` span gets a distinct ``span_ids`` key and eval can score
        BOTH attempts of a redirect_parser hero trace.
        """
        self._attempt_seq += 1
        return self._attempt_seq

    @contextmanager
    def attempt_span(self, number: int, *, attempt_id: int | None = None):
        span = self._tracer.start_span("repro_attempt", context=self._root_ctx)
        span.set_attribute("attempt.number", number)
        # Key on the run-unique attempt id (fall back to the display number when an
        # id isn't supplied) so a redirect_parser re-parse can't overwrite a prior
        # attempt's captured span id.
        key = attempt_id if attempt_id is not None else number
        span.set_attribute("attempt.id", key)
        # Record the span id (16-hex, lowercase — AX context.span_id format) so the
        # evaluator can log onto this exact span later without querying it back.
        self.span_ids[key] = format(span.get_span_context().span_id, "016x")
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

    span_ids: dict[int, str] = {}

    def __enter__(self) -> "NullRunTrace":
        return self

    def __exit__(self, *a) -> None:
        return None

    def new_attempt_id(self) -> int:
        return 0

    @contextmanager
    def attempt_span(self, number: int, *, attempt_id: int | None = None):
        yield None

    @contextmanager
    def child_span(self, name: str, parent):
        yield None

    @contextmanager
    def claude_span(self, name: str, *, attempt_number: int | None = None):
        yield None
