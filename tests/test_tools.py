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

    def test_employee_lookup_vp_without_manager_handles_nan_gracefully(self):
        # E010 Lisa Park has no manager_id in CSV (blank/NaN)
        tool = EmployeeBudgetLookupTool()
        res = tool.execute("E010", telemetry=self.telemetry)
        self.assertTrue(res["found"])
        self.assertIn("None (Executive/VP)", res["employee"]["manager_name"])
        self.assertNotIn("nan", str(res["evidence"][0].finding).lower())

    def test_software_catalog_lookup_empty_product_name(self):
        # Empty product name must not match every catalog row
        tool = SoftwareCatalogLookupTool()
        res = tool.execute(product_name="", category="", vendor_name="", telemetry=self.telemetry)
        self.assertFalse(res["has_overlap"])
        self.assertFalse(res["is_expansion"])
        self.assertIn("missing", res["evidence"][0].finding.lower())

    def test_software_catalog_lookup_expansion_vs_overlap(self):
        tool = SoftwareCatalogLookupTool()
        # SignFlow Add-on is an expansion of approved tool SW010
        addon_res = tool.execute(product_name="SignFlow Add-on", category="E-signature", vendor_name="SignFlow", telemetry=self.telemetry)
        self.assertTrue(addon_res["is_expansion"])
        self.assertFalse(addon_res["has_overlap"])

        # BrandBoard Enterprise in Design & Creative is an overlapping alternative (PixelCraft/CreativeSuite exist)
        overlap_res = tool.execute(product_name="BrandBoard Enterprise", category="Design & Creative", vendor_name="BrandBoard", telemetry=self.telemetry)
        self.assertTrue(overlap_res["has_overlap"])
        self.assertFalse(overlap_res["is_expansion"])

    def test_vendor_security_lookup_approved(self):
        tool = VendorSecurityLookupTool()
        res = tool.execute("SignFlow", telemetry=self.telemetry)
        self.assertTrue(res["api_available"])
        self.assertEqual(res["security_status"], "approved")
        self.assertFalse(res["is_expired"])
        self.assertFalse(res["has_conflict"])

    def test_vendor_security_lookup_no_date_is_not_expired(self):
        # BrandBoard has no security review date (onboarding incomplete). Must NOT be labeled expired!
        tool = VendorSecurityLookupTool()
        res = tool.execute("BrandBoard", telemetry=self.telemetry)
        self.assertFalse(res["is_expired"])
        self.assertEqual(res["security_status"], "not_completed")

    def test_vendor_security_lookup_api_outage_503(self):
        tool = VendorSecurityLookupTool()
        res = tool.execute("NimbusAI", telemetry=self.telemetry)
        # NimbusAI mock endpoint throws 503 outage
        self.assertFalse(res["api_available"])
        self.assertFalse(res["is_expired"])  # Outage must not infer expired!
        self.assertIsNotNone(res["api_error_detail"])
        self.assertIn("503", str(res["api_error_detail"]))

    def test_vendor_security_lookup_api_404_not_found(self):
        # Unknown vendor returns 404 in mock API
        tool = VendorSecurityLookupTool()
        res = tool.execute("NonExistentVendorXYZ", telemetry=self.telemetry)
        self.assertTrue(res["api_available"])
        self.assertEqual(res["api_status"], "not_found")
        self.assertFalse(res["is_expired"])
        self.assertIn("404", res["evidence"][0].finding)

    def test_vendor_security_lookup_conflict_and_expiry(self):
        tool = VendorSecurityLookupTool()
        res = tool.execute("SignalWatch", telemetry=self.telemetry)
        self.assertTrue(res["is_expired"])
        self.assertTrue(res["has_conflict"])


if __name__ == "__main__":
    unittest.main()
