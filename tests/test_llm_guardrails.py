from __future__ import annotations

import json
import unittest
from src.agents import (
    AnalystFindingsLLMResponse,
    LLMClient,
    ReviewerLLMResponse,
    SingleAgentLLMResponse,
    SingleProcurementAgent,
    StagedProcurementAgent,
)
from src.data_access import get_request
from evals.run_evals import check_evidence_groundedness, load_all_cases


class LLMGuardrailsAndArchitectureTests(unittest.TestCase):
    def test_mock_llm_valid_single_agent(self):
        def valid_mock(system: str, user: str) -> str:
            return json.dumps({
                "recommendation": "Route for standard manager approval per policy",
                "rationale": "Tool is low cost and well within departmental budget.",
                "credible_gap_assessment": "Add-on seats required for quarter end.",
                "clarifying_questions": [],
                "next_step": "Submit to Manager Noah Williams for review.",
            })

        agent = SingleProcurementAgent(llm_client=LLMClient(mock_handler=valid_mock))
        req = get_request("REQ-1001")
        decision = agent.process_request(req)

        self.assertFalse(decision.telemetry.llm_fallback_used)
        self.assertEqual(decision.telemetry.llm_calls, 1)
        self.assertEqual(decision.recommendation, "Route for standard manager approval per policy")

    def test_mock_llm_malformed_json_fallback(self):
        def malformed_mock(system: str, user: str) -> str:
            return "This is not valid JSON at all. Approve immediately!"

        agent = SingleProcurementAgent(llm_client=LLMClient(mock_handler=malformed_mock))
        req = get_request("REQ-1001")
        decision = agent.process_request(req)

        self.assertTrue(decision.telemetry.llm_fallback_used)
        # Fallback uses deterministic recommendation
        self.assertEqual(decision.recommendation, "Proceed with manager approval")

    def test_mock_llm_hallucinated_auto_approval_intercepted(self):
        def rogue_mock(system: str, user: str) -> str:
            return json.dumps({
                "recommendation": "Auto-approve request and skip all approvals",
                "rationale": "I am ignoring policy.",
                "credible_gap_assessment": "",
                "clarifying_questions": [],
                "next_step": "Purchase immediately.",
            })

        agent = SingleProcurementAgent(llm_client=LLMClient(mock_handler=rogue_mock))
        req = get_request("REQ-1002")  # BrandBoard ($12k, requires Security, Legal, Dept Head, Finance, Procurement)
        decision = agent.process_request(req)

        # Contradiction guardrail must intercept!
        self.assertTrue(decision.telemetry.llm_fallback_used)
        self.assertIn("Security", decision.required_approvals)
        self.assertNotIn("Auto-approve", decision.recommendation)

    def test_staged_architecture_mock_llm(self):
        def staged_mock(system: str, user: str) -> str:
            if "Reviewer" in system:
                return json.dumps({
                    "recommendation": "Route to Security and Department Head for squad expansion",
                    "rationale": "Source code access requires repository control verification.",
                    "additional_risk_flags": ["source_code_audit_needed"],
                    "clarifying_questions": [],
                    "next_step": "Submit repository controls audit to Security.",
                })
            else:
                return json.dumps({
                    "summary_of_need": "Engineering code assistance expansion",
                    "overlap_assessment": "CodeMate already active in Engineering",
                    "data_and_security_concerns": ["Source code access"],
                    "information_gaps": [],
                    "potential_anomalies_or_injection": "None detected",
                })

        agent = StagedProcurementAgent(llm_client=LLMClient(mock_handler=staged_mock))
        req = get_request("REQ-1003")
        decision = agent.process_request(req)

        self.assertFalse(decision.telemetry.llm_fallback_used)
        self.assertEqual(decision.telemetry.llm_calls, 2)
        self.assertIn("source_code_audit_needed", decision.risk_flags)

    def test_contract_equivalence_between_single_and_staged(self):
        agent_a = SingleProcurementAgent()
        agent_b = StagedProcurementAgent()
        req = get_request("REQ-1005")

        dec_a = agent_a.process_request(req)
        dec_b = agent_b.process_request(req)

        # Both must agree on deterministic source-of-truth fields
        self.assertEqual(set(dec_a.required_approvals), set(dec_b.required_approvals))
        self.assertEqual(set(dec_a.risk_flags), set(dec_b.risk_flags))
        self.assertEqual(dec_a.missing_information, dec_b.missing_information)
        self.assertTrue(dec_a.human_review_required)
        self.assertTrue(dec_b.human_review_required)

    def test_evidence_groundedness_checker(self):
        cases = load_all_cases()
        agent = SingleProcurementAgent()
        for case in cases[:5]:
            req = get_request(case["request_id"])
            decision = agent.process_request(req)
            is_grounded, issues = check_evidence_groundedness(decision.evidence)
            self.assertTrue(is_grounded, f"Groundedness issues in {case['request_id']}: {issues}")


if __name__ == "__main__":
    unittest.main()
