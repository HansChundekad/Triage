"""Evaluator (Phase 7B): LLM judges + code honesty check, per attempt.

Judge engine is local (phoenix.evals); results log to the active trace backend
(Arize AX via spans.update_evaluations; Phoenix annotations as fallback).
"""
