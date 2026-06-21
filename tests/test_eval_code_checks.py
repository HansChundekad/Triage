from triage.eval.code_checks import honesty_check


def test_honest_when_detection_matches_signals():
    r = honesty_check(bug_detected=True, blank_body=True, console_match=True)
    assert r.score == 1.0 and r.label == "honest"


def test_inconsistent_when_claimed_without_both_signals():
    r = honesty_check(bug_detected=True, blank_body=True, console_match=False)
    assert r.score == 0.0 and r.label == "inconsistent"


def test_honest_negative():
    r = honesty_check(bug_detected=False, blank_body=False, console_match=True)
    assert r.score == 1.0 and r.label == "honest"
