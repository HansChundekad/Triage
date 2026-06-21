from __future__ import annotations

import json
import re

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from backend.run_manager import RunRegistry

ISSUE_RE = re.compile(r"^https://github\.com/[^/]+/[^/]+/issues/\d+/?$")

app = FastAPI(title="TRIAGE frontend backend")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)
_registry = RunRegistry()


class RunRequest(BaseModel):
    issueUrl: str


@app.post("/api/runs")
async def start_run(req: RunRequest):
    if not ISSUE_RE.match(req.issueUrl.strip()):
        raise HTTPException(422, "not a GitHub issue URL")
    return {"runId": _registry.create(req.issueUrl.strip())}


@app.get("/api/runs/{run_id}")
def snapshot(run_id: str):
    try:
        return _registry.snapshot(run_id)
    except KeyError:
        raise HTTPException(404, "unknown run")


@app.get("/api/runs/{run_id}/stream")
async def stream(run_id: str):
    if not _registry.has(run_id):
        raise HTTPException(404, "unknown run")
    async def gen():
        async for name, data in _registry.stream(run_id):
            yield {"event": name, "data": json.dumps(data)}
    return EventSourceResponse(gen())


@app.get("/api/replays")
def replays():
    # The frontend ships its own bundled fixture; this lists server-side ones (none yet).
    return []
