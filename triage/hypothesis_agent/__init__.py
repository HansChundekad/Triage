"""HypothesisAgent package — Phase 5 real Claude reasoning."""
from .agent import (
    format_diagnosis_message,
    make_diagnosis_callback,
    route_diagnosis,
    run,
)
from .reasoning import Diagnosis, diagnose

__all__ = [
    "run",
    "make_diagnosis_callback",
    "route_diagnosis",
    "format_diagnosis_message",
    "Diagnosis",
    "diagnose",
]
