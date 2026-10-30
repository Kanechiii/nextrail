"""Auditable, guest-first, fail-closed specialist-agent workflow."""

from .agents import OrchestrationError, StageRecord, OrchestrationResult
from .engine import orchestrate

__all__ = ["OrchestrationError", "StageRecord", "OrchestrationResult", "orchestrate"]
