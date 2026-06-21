"""ReproReport — the frozen frontend contract + Claude output schema."""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Optional

import jsonschema


@dataclass
class Issue:
    url: str; title: str; summary: str


@dataclass
class ReproStep:
    n: int; action: str; status: str; screenshot_ref: str


@dataclass
class RootCause:
    hypothesis: str; mechanism: str; confidence: str


@dataclass
class Evidence:
    console_error: str; blank_screen: bool; body_snippet: str


@dataclass
class Attempt:
    number: int; session_replay_url: str; bug_detected: bool


@dataclass
class EvalScores:
    repro_fidelity: Optional[float] = None
    root_cause_correctness: Optional[float] = None


@dataclass
class ReproReport:
    issue: Issue
    verdict: str
    repro_steps: list[ReproStep]
    root_cause: RootCause
    evidence: Evidence
    attempts: list[Attempt]
    eval_scores: Optional[EvalScores]
    generated_at: str

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "ReproReport":
        es = d.get("eval_scores")
        return cls(
            issue=Issue(**d["issue"]),
            verdict=d["verdict"],
            repro_steps=[ReproStep(**s) for s in d["repro_steps"]],
            root_cause=RootCause(**d["root_cause"]),
            evidence=Evidence(**d["evidence"]),
            attempts=[Attempt(**a) for a in d["attempts"]],
            eval_scores=EvalScores(**es) if es else None,
            generated_at=d["generated_at"],
        )


REPORT_JSON_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["issue", "verdict", "repro_steps", "root_cause", "evidence",
                 "attempts", "eval_scores", "generated_at"],
    "properties": {
        "issue": {"type": "object", "additionalProperties": False,
                  "required": ["url", "title", "summary"],
                  "properties": {"url": {"type": "string"}, "title": {"type": "string"},
                                 "summary": {"type": "string"}}},
        "verdict": {"type": "string", "enum": ["reproduced", "not_reproduced"]},
        "repro_steps": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "required": ["n", "action", "status", "screenshot_ref"],
            "properties": {"n": {"type": "integer"}, "action": {"type": "string"},
                           "status": {"type": "string", "enum": ["ok", "fail", "crash"]},
                           "screenshot_ref": {"type": "string"}}}},
        "root_cause": {"type": "object", "additionalProperties": False,
                       "required": ["hypothesis", "mechanism", "confidence"],
                       "properties": {"hypothesis": {"type": "string"},
                                      "mechanism": {"type": "string"},
                                      "confidence": {"type": "string",
                                                     "enum": ["high", "medium", "low"]}}},
        "evidence": {"type": "object", "additionalProperties": False,
                     "required": ["console_error", "blank_screen", "body_snippet"],
                     "properties": {"console_error": {"type": "string"},
                                    "blank_screen": {"type": "boolean"},
                                    "body_snippet": {"type": "string"}}},
        "attempts": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "required": ["number", "session_replay_url", "bug_detected"],
            "properties": {"number": {"type": "integer"},
                           "session_replay_url": {"type": "string"},
                           "bug_detected": {"type": "boolean"}}}},
        "eval_scores": {"type": ["object", "null"], "additionalProperties": False,
                        "properties": {"repro_fidelity": {"type": ["number", "null"]},
                                       "root_cause_correctness": {"type": ["number", "null"]}}},
        "generated_at": {"type": "string"},
    },
}

# Schema handed to Claude: only the fields the model should generate. Server fills
# attempts[].session_replay_url, eval_scores, generated_at after generation.
CLAUDE_OUTPUT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["verdict", "repro_steps", "root_cause", "evidence"],
    "properties": {
        "verdict": REPORT_JSON_SCHEMA["properties"]["verdict"],
        "repro_steps": REPORT_JSON_SCHEMA["properties"]["repro_steps"],
        "root_cause": REPORT_JSON_SCHEMA["properties"]["root_cause"],
        "evidence": REPORT_JSON_SCHEMA["properties"]["evidence"],
    },
}


def validate_report(d: dict) -> None:
    jsonschema.validate(instance=d, schema=REPORT_JSON_SCHEMA)
