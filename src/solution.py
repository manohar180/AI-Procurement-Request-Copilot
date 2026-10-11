from __future__ import annotations

from typing import Any
from src.contracts import Architecture, ProcurementDecision
from src.data_access import get_request
from src.agents import SingleProcurementAgent, StagedProcurementAgent

_single_agent = SingleProcurementAgent()
_staged_agent = StagedProcurementAgent()


def handle_request(request_or_id: str | dict[str, Any], architecture: Architecture = "single") -> ProcurementDecision:
    """Assessment adapter.

    Executes either the single-agent baseline or the staged/two-agent architecture
    on the specified purchase request and returns a validated ProcurementDecision.
    Accepts either a string request_id or a raw request dictionary for custom simulation.
    """
    if isinstance(request_or_id, dict):
        request = request_or_id
    elif isinstance(request_or_id, str):
        request = get_request(request_or_id)
    else:
        raise TypeError(f"Expected str request_id or dict, got {type(request_or_id).__name__}")

    if architecture == "single":
        return _single_agent.process_request(request)
    elif architecture == "staged":
        return _staged_agent.process_request(request)
    else:
        raise ValueError(f"Unknown architecture: {architecture}. Expected 'single' or 'staged'.")
