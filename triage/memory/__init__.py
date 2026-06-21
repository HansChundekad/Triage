"""Phase 7.5 outer loop: read prior-run history from Arize and distill a hint.

`load_learned_context` is the single guarded entry point the run drivers call at
run start. It NEVER raises and NEVER blocks past its timeout: on flag OFF, error,
timeout, or empty history it returns None and the run falls back to the proven
inner loop.
"""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout

from triage.memory.distill import distill_hint
from triage.memory.query import query_prior_runs

logger = logging.getLogger(__name__)


def load_learned_context(cfg, *, timeout_s: float = 8.0) -> str | None:
    """Query Arize for prior-run history of this issue → one-line hint, or None.

    Never raises; never blocks past timeout_s. NB: a hung query_prior_runs worker
    thread is abandoned (shutdown(wait=False, cancel_futures=True)) rather than
    waited on, so a stuck Phoenix call can never delay a repro run.
    """
    if not getattr(cfg, "outer_loop_enabled", False):
        return None
    pool = ThreadPoolExecutor(max_workers=1)
    try:
        future = pool.submit(query_prior_runs, cfg, issue_url=cfg.github_issue_url)
        prior = future.result(timeout=timeout_s)
        return distill_hint(prior)
    except FuturesTimeout:
        logger.warning("[memory] prior-run query timed out (%.1fs) — inner loop", timeout_s)
        return None
    except Exception as exc:  # noqa: BLE001 — memory must never wedge a run
        logger.warning("[memory] prior-run query skipped (non-fatal): %s", exc)
        return None
    finally:
        pool.shutdown(wait=False, cancel_futures=True)
