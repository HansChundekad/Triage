from triage.eval.ground_truth import PLANTED_BUG
from triage.repro_agent.browser import CRASH_SUBSTRING


def test_ground_truth_matches_detection_fingerprint():
    assert PLANTED_BUG.console_fingerprint == CRASH_SUBSTRING
    assert "blank" in PLANTED_BUG.symptom.lower()
    assert PLANTED_BUG.root_cause  # non-empty mechanistic statement
