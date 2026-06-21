"""RunArtifacts — per-run store bridging captured evidence to eval (7B) + synthesis (7C).

ReproResultPayload cannot carry screenshots and shared/band.py is untouched, so the
captured PNGs + per-attempt evidence are persisted here instead.
"""
from __future__ import annotations

import base64
import json
import os
from datetime import datetime, timezone
from pathlib import Path


class RunArtifacts:
    def __init__(self, root_dir: str | os.PathLike):
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
        self._dir = Path(root_dir) / stamp
        (self._dir / "screenshots").mkdir(parents=True, exist_ok=True)
        self._attempts_path = self._dir / "attempts.json"

    @property
    def run_dir(self) -> str:
        return str(self._dir)

    def save_screenshot(self, attempt: int, step: int, png_b64: str) -> str:
        rel = f"screenshots/attempt{attempt}_step{step}.png"
        (self._dir / rel).write_bytes(base64.b64decode(png_b64))
        return rel

    def record_attempt(self, record: dict) -> None:
        data = self.load_attempts()
        data.append(record)
        self._attempts_path.write_text(json.dumps(data, indent=2))

    def load_attempts(self) -> list[dict]:
        if not self._attempts_path.exists():
            return []
        return json.loads(self._attempts_path.read_text())

    def write_report(self, report: dict) -> str:
        path = self._dir / "report.json"
        path.write_text(json.dumps(report, indent=2))
        return str(path)


class NullRunArtifacts:
    run_dir = ""

    def save_screenshot(self, attempt: int, step: int, png_b64: str) -> str:
        return ""

    def record_attempt(self, record: dict) -> None:
        return None

    def load_attempts(self) -> list[dict]:
        return []

    def write_report(self, report: dict) -> str:
        return ""
