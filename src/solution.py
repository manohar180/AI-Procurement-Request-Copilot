from __future__ import annotations

from src.contracts import Architecture, ProcurementDecision
from src.data_access import get_request
from src.agents import SingleProcurementAgent, StagedProcurementAgent

_single_agent = SingleProcurementAgent()
_staged_agent = StagedProcurementAgent()


def handle_request(request_id: str, architecture: Architecture = "single") -> ProcurementDecision:
    """Assessment adapter.

    Executes either the single-agent baseline or the staged/two-agent architecture
    on the specified purchase request and returns a validated ProcurementDecision.
    """
    request = get_request(request_id)
    if architecture == "single":
        return _single_agent.process_request(request)
    elif architecture == "staged":
        return _staged_agent.process_request(request)
    else:
        raise ValueError(f"Unknown architecture: {architecture}. Expected 'single' or 'staged'.")
