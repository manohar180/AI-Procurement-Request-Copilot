from __future__ import annotations

import unittest
from src.contracts import ProcurementDecision
from src.data_access import load_requests
from src.solution import handle_request


class SolutionIntegrationTests(unittest.TestCase):
    def test_all_requests_single_architecture(self):
        requests = load_requests()
        for r in requests:
            req_id = r["request_id"]
            decision = handle_request(req_id, architecture="single")
            self.assertIsInstance(decision, ProcurementDecision)
            self.assertEqual(decision.request_id, req_id)
            self.assertTrue(decision.human_review_required)
            self.assertGreater(len(decision.evidence), 0)
            self.assertIsNotNone(decision.recommendation)
            self.assertIsNotNone(decision.next_step)
            self.assertIsNotNone(decision.telemetry)
            self.assertGreaterEqual(decision.telemetry.tool_calls, 3)

    def test_all_requests_staged_architecture(self):
        requests = load_requests()
        for r in requests:
            req_id = r["request_id"]
            decision = handle_request(req_id, architecture="staged")
            self.assertIsInstance(decision, ProcurementDecision)
            self.assertEqual(decision.request_id, req_id)
            self.assertTrue(decision.human_review_required)
            self.assertGreater(len(decision.evidence), 0)
            self.assertIsNotNone(decision.recommendation)
            self.assertIsNotNone(decision.next_step)
            self.assertIsNotNone(decision.telemetry)
            self.assertGreaterEqual(decision.telemetry.tool_calls, 3)


if __name__ == "__main__":
    unittest.main()
