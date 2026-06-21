"""Planted-bug ground truth — single source of truth for the root-cause judge.

Deliberately NOT shown to the agents; only the evaluator sees it.
"""
from __future__ import annotations

from dataclasses import dataclass

from triage.repro_agent.browser import CRASH_SUBSTRING


@dataclass(frozen=True)
class PlantedBug:
    symptom: str
    console_fingerprint: str
    root_cause: str


PLANTED_BUG = PlantedBug(
    symptom=(
        "Deleting the last remaining task makes the app render a blank screen "
        "instead of an empty-list state."
    ),
    console_fingerprint=CRASH_SUBSTRING,
    root_cause=(
        "After the final delete empties the tasks array, the render path still "
        "dereferences an element/length of that now-empty array (e.g. items[0] / "
        "items.length on undefined), throwing a TypeError that blanks the page."
    ),
)
