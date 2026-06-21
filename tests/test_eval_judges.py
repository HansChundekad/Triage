from triage.eval.judges import (
    build_fidelity_input, build_root_cause_input,
    FIDELITY_CHOICES, ROOT_CAUSE_CHOICES,
)
from triage.eval.ground_truth import PLANTED_BUG


def test_fidelity_input_carries_issue_and_evidence():
    attempt = {"bug_detected": True, "evidence": ["blank body"],
               "console_errors": ["Cannot read properties of undefined"]}
    out = build_fidelity_input("app goes blank when I delete my last task", attempt)
    assert "delete my last task" in out["input"]
    assert "Cannot read properties of undefined" in out["output"]
    assert "BUG REPRODUCED" in out["output"] or "True" in out["output"]


def test_root_cause_input_includes_ground_truth_and_hypothesis():
    out = build_root_cause_input("app goes blank...", "reads items[0] after delete")
    assert PLANTED_BUG.root_cause in out["reference"]
    assert "reads items[0] after delete" in out["output"]


def test_choice_maps_are_scored():
    assert FIDELITY_CHOICES["reproduced"] == 1.0
    assert FIDELITY_CHOICES["not_reproduced"] == 0.0
    assert ROOT_CAUSE_CHOICES["correct"] == 1.0
    assert ROOT_CAUSE_CHOICES["incorrect"] == 0.0
