from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from triage.tracing.run_context import RunTrace, NullRunTrace


def _tracer_and_exporter():
    provider = TracerProvider()
    exporter = InMemorySpanExporter()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    return provider.get_tracer("triage-test"), exporter


def test_run_trace_builds_nested_tree():
    tracer, exporter = _tracer_and_exporter()
    with RunTrace(tracer, issue_url="http://issue", app_url="http://app") as run:
        with run.attempt_span(1) as attempt:
            with run.child_span("browser_execution", attempt) as be:
                with run.child_span("stagehand_action", be) as step:
                    step.set_attribute("step.index", 1)
        with run.claude_span("hypothesis_generation", attempt_number=1):
            pass

    spans = {s.name: s for s in exporter.get_finished_spans()}
    assert {"triage_run", "repro_attempt", "browser_execution",
            "stagehand_action", "hypothesis_generation"} <= set(spans)
    root = spans["triage_run"]
    # repro_attempt's parent is the root span
    assert spans["repro_attempt"].parent.span_id == root.context.span_id
    # stagehand_action nests under browser_execution
    assert spans["stagehand_action"].parent.span_id == spans["browser_execution"].context.span_id
    # claude span parented under root, tagged with the attempt number
    assert spans["hypothesis_generation"].parent.span_id == root.context.span_id
    assert spans["hypothesis_generation"].attributes["attempt.number"] == 1
    assert spans["repro_attempt"].attributes["attempt.number"] == 1
    assert root.attributes["github.issue_url"] == "http://issue"


def test_null_run_trace_is_safe_noop():
    run = NullRunTrace()
    with run as r:
        with r.attempt_span(1) as a:
            with r.child_span("x", a) as c:
                assert c is None
        with r.claude_span("y", attempt_number=2) as c:
            assert c is None
