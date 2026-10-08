from __future__ import annotations

import unittest
from src.telemetry import RunTelemetryCounter
from src.tools import (
    EmployeeBudgetLookupTool,
    ProcurementPolicyCheckerTool,
    SoftwareCatalogLookupTool,
    VendorSecurityLookupTool,
)


class ToolsTests(unittest.TestCase):
    def setUp(self):
        self.telemetry = RunTelemetryCounter()

    def test_employee_budget_lookup(self):
        tool = EmployeeBudgetLookupTool()
        res = tool.execute("E001", telemetry=self.telemetry)
        self.assertTrue(res["found"])
        self.assertEqual(res["employee"]["name"], "Sarah Lee")
        self.assertEqual(res["employee"]["department"], "Marketing")
        self.assertEqual(res["budget"]["available_usd"], 15000)
        self.assertGreater(len(res["evidence"]), 0)
        self.assertEqual(self.telemetry.tool_calls, 1)

    def test_software_catalog_lookup(self):
        tool = SoftwareCatalogLookupTool()
        # REQ-1002 category overlap test
        res = tool.execute(product_name="BrandBoard Enterprise", category="Design & Creative", vendor_name="BrandBoard", telemetry=self.telemetry)
        self.assertTrue(res["has_overlap"])
        self.assertGreater(len(res["overlapping_tools"]), 0)

    def test_vendor_security_lookup_approved(self):
        tool = VendorSecurityLookupTool()
        res = tool.execute("SignFlow", telemetry=self.telemetry)
        self.assertTrue(res["api_available"])
        self.assertEqual(res["security_status"], "approved")
        self.assertFalse(res["is_expired"])
        self.assertFalse(res["has_conflict"])

    def test_vendor_security_lookup_api_outage(self):
        tool = VendorSecurityLookupTool()
        res = tool.execute("NimbusAI", telemetry=self.telemetry)
        # NimbusAI mock endpoint throws 503 outage
        self.assertFalse(res["api_available"])
        self.assertIsNotNone(res["api_error_detail"])
        self.assertIn("503", str(res["api_error_detail"]))

    def test_vendor_security_lookup_conflict_and_expiry(self):
        tool = VendorSecurityLookupTool()
        res = tool.execute("SignalWatch", telemetry=self.telemetry)
        self.assertTrue(res["is_expired"])
        self.assertTrue(res["has_conflict"])


if __name__ == "__main__":
    unittest.main()
