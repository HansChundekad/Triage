import base64
import json
from pathlib import Path

from triage.tracing.artifacts import RunArtifacts, NullRunArtifacts


def test_run_artifacts_persists_screenshot_and_records(tmp_path):
    art = RunArtifacts(tmp_path)
    png = base64.b64encode(b"\x89PNG fake bytes").decode()
    ref = art.save_screenshot(attempt=1, step=2, png_b64=png)
    assert ref == "screenshots/attempt1_step2.png"
    assert (Path(art.run_dir) / ref).read_bytes() == b"\x89PNG fake bytes"

    art.record_attempt({"attempt": 1, "bug_detected": False})
    art.record_attempt({"attempt": 2, "bug_detected": True})
    assert [a["bug_detected"] for a in art.load_attempts()] == [False, True]

    path = art.write_report({"verdict": "reproduced"})
    assert json.loads(Path(path).read_text())["verdict"] == "reproduced"


def test_null_run_artifacts_is_safe_noop():
    art = NullRunArtifacts()
    assert art.save_screenshot(1, 1, "ignored") == ""
    art.record_attempt({"x": 1})
    assert art.load_attempts() == []
    art.write_report({"y": 2})  # no raise
