from __future__ import annotations

from typing import Any
import requests

from src.contracts import EvidenceItem
from src.data_access import (
    load_budgets,
    load_employees,
    load_purchase_history,
    load_software_catalog,
    load_vendors,
)
from src.policy_engine import (
    REFERENCE_DATE,
    PolicyEvaluationResult,
    evaluate_procurement_policy,
    is_date_expired,
)
from src.telemetry import RunTelemetryCounter
from src.vendor_client import get_vendor_risk


class EmployeeBudgetLookupTool:
    """Tool 1: Looks up requester profile, reporting hierarchy, and department budget."""

    name = "employee_budget_tool"

    def execute(self, requester_id: str, telemetry: RunTelemetryCounter | None = None) -> dict[str, Any]:
        if telemetry:
            telemetry.record_tool_call(self.name)

        employees_df = load_employees()
        budgets_df = load_budgets()

        emp_row = employees_df[employees_df["employee_id"] == requester_id]
        if emp_row.empty:
            return {
                "found": False,
                "requester_id": requester_id,
                "evidence": [
                    EvidenceItem(
                        source=self.name,
                        finding=f"Requester ID {requester_id} not found in employee directory.",
                        reference="data/employees.csv",
                    )
                ],
            }

        emp = emp_row.iloc[0].to_dict()
        manager_id = emp.get("manager_id")
        manager_name = "None"
        if manager_id:
            mgr_row = employees_df[employees_df["employee_id"] == manager_id]
            if not mgr_row.empty:
                manager_name = mgr_row.iloc[0]["name"]

        dept = emp.get("department", "")
        dept_budget_row = budgets_df[budgets_df["department"] == dept]
        budget_info: dict[str, Any] = {}
        if not dept_budget_row.empty:
            budget_info = dept_budget_row.iloc[0].to_dict()
            available = budget_info.get("available_usd", 0)
            annual = budget_info.get("annual_software_budget_usd", 0)
            committed = budget_info.get("committed_usd", 0)
            budget_finding = (
                f"Department: {dept} (Annual Budget: ${annual:,.2f}, "
                f"Committed: ${committed:,.2f}, Available: ${available:,.2f})."
            )
        else:
            budget_finding = f"Department '{dept}' not found in budget database."

        emp_finding = (
            f"Requester: {emp['name']} ({emp.get('level', 'IC')}, {emp.get('country', '')}), "
            f"Department: {dept}, Manager: {manager_name} ({manager_id or 'None'}). {budget_finding}"
        )

        return {
            "found": True,
            "employee": {**emp, "manager_name": manager_name},
            "budget": budget_info,
            "evidence": [
                EvidenceItem(
                    source=self.name,
                    finding=emp_finding,
                    reference=f"data/employees.csv:{requester_id}, data/department_budgets.csv:{dept}",
                )
            ],
        }


class SoftwareCatalogLookupTool:
    """Tool 2: Identifies catalog overlap, existing software alternatives, and purchase history."""

    name = "software_catalog_tool"

    def execute(
        self,
        product_name: str,
        category: str = "",
        vendor_name: str = "",
        telemetry: RunTelemetryCounter | None = None,
    ) -> dict[str, Any]:
        if telemetry:
            telemetry.record_tool_call(self.name)

        catalog_df = load_software_catalog()
        purchases_df = load_purchase_history()

        prod_norm = (product_name or "").lower().strip()
        cat_norm = (category or "").lower().strip()
        ven_norm = (vendor_name or "").lower().strip()

        exact_matches = []
        category_matches = []
        vendor_matches = []

        for _, row in catalog_df.iterrows():
            item = row.to_dict()
            name_curr = str(item.get("product_name", "")).lower()
            cat_curr = str(item.get("category", "")).lower()
            ven_curr = str(item.get("vendor_name", "")).lower()

            # Exact or core product match (e.g. "TaskFlow Pro" vs "TaskFlow", "SignFlow Add-on" vs "SignFlow")
            if (
                prod_norm in name_curr
                or name_curr in prod_norm
                or (ven_norm and ven_norm in name_curr)
            ):
                exact_matches.append(item)
            elif cat_norm and (cat_norm in cat_curr or cat_curr in cat_norm):
                category_matches.append(item)
            elif ven_norm and (ven_norm == ven_curr):
                vendor_matches.append(item)

        # Look up purchase history
        related_purchases = []
        for _, row in purchases_df.iterrows():
            p = row.to_dict()
            p_prod = str(p.get("product_name", "")).lower()
            p_ven = str(p.get("vendor_name", "")).lower()
            if (
                prod_norm in p_prod
                or p_prod in prod_norm
                or (ven_norm and ven_norm == p_ven)
            ):
                related_purchases.append(p)

        has_overlap = bool(exact_matches or category_matches)
        evidence_items: list[EvidenceItem] = []

        if exact_matches:
            match_names = [f"{m['product_name']} ({m['software_id']}, {m.get('scope', 'Company-wide')})" for m in exact_matches]
            evidence_items.append(
                EvidenceItem(
                    source=self.name,
                    finding=f"Existing approved software already in catalog matching request: {', '.join(match_names)}.",
                    reference=f"data/software_catalog.csv:{','.join(m['software_id'] for m in exact_matches)}",
                )
            )
        elif category_matches:
            cat_tool_names = [f"{m['product_name']} ({m['software_id']}, Scope: {m.get('scope', '')})" for m in category_matches]
            evidence_items.append(
                EvidenceItem(
                    source=self.name,
                    finding=f"Category '{category}' has existing approved software in catalog: {', '.join(cat_tool_names)}. Potential overlap.",
                    reference=f"data/software_catalog.csv:{','.join(m['software_id'] for m in category_matches)}",
                )
            )
        else:
            evidence_items.append(
                EvidenceItem(
                    source=self.name,
                    finding=f"No direct existing product or category match found in catalog for '{product_name}' ({category}).",
                    reference="data/software_catalog.csv",
                )
            )

        if related_purchases:
            hist_str = ", ".join(f"{p['purchase_id']} (${p['annual_amount_usd']:,.2f} on {p['purchase_date']})" for p in related_purchases)
            evidence_items.append(
                EvidenceItem(
                    source=self.name,
                    finding=f"Prior purchase history found for vendor/product: {hist_str}.",
                    reference=f"data/purchase_history.csv:{related_purchases[0]['purchase_id']}",
                )
            )

        return {
            "has_overlap": has_overlap,
            "exact_matches": exact_matches,
            "category_matches": category_matches,
            "overlapping_tools": exact_matches or category_matches,
            "related_purchases": related_purchases,
            "evidence": evidence_items,
        }


class VendorSecurityLookupTool:
    """Tool 3: Queries internal vendor registry and external vendor-risk service."""

    name = "vendor_security_tool"

    def execute(self, vendor_name: str, telemetry: RunTelemetryCounter | None = None) -> dict[str, Any]:
        if telemetry:
            telemetry.record_tool_call(self.name)

        vendors_df = load_vendors()
        vendor_row = vendors_df[vendors_df["vendor_name"].str.lower() == (vendor_name or "").lower()]

        registry_info: dict[str, Any] = {}
        is_new_vendor = True
        sec_review_date = None
        legal_terms_status = "Unknown"
        registry_sec_status = "Unknown"

        if not vendor_row.empty:
            registry_info = vendor_row.iloc[0].to_dict()
            is_new_vendor = str(registry_info.get("procurement_status", "")).lower() == "new"
            sec_review_date = registry_info.get("security_review_date")
            legal_terms_status = str(registry_info.get("legal_terms_status", "Unknown"))
            registry_sec_status = str(registry_info.get("security_status", "Unknown"))

        # Query mock external service via vendor_client
        api_info: dict[str, Any] | None = None
        api_available = True
        api_error_detail: str | None = None

        try:
            api_info = get_vendor_risk(vendor_name)
        except requests.RequestException as e:
            api_available = False
            api_error_detail = str(e)
        except Exception as e:
            api_available = False
            api_error_detail = str(e)

        # Check expiration and conflicts
        is_expired = False
        effective_sec_status = registry_sec_status.lower()
        effective_review_date = sec_review_date
        processes_personal_data = False
        stores_data_outside_region = False

        if api_available and api_info:
            api_sec_status = str(api_info.get("security_review_status", "")).lower()
            api_review_date = api_info.get("last_review_date")
            processes_personal_data = bool(api_info.get("processes_personal_data", False))
            stores_data_outside_region = bool(api_info.get("stores_data_outside_region", False))

            if api_sec_status:
                effective_sec_status = api_sec_status
            if api_review_date:
                effective_review_date = api_review_date

            if api_sec_status == "expired":
                is_expired = True

        if effective_review_date:
            if is_date_expired(str(effective_review_date), reference_date=REFERENCE_DATE):
                is_expired = True

        has_conflict = False
        if api_available and api_info:
            reg_status_clean = registry_sec_status.lower()
            api_status_clean = str(api_info.get("security_review_status", "")).lower()
            if reg_status_clean == "approved" and api_status_clean in ("expired", "not_completed"):
                has_conflict = True

        evidence_items: list[EvidenceItem] = []

        if registry_info:
            evidence_items.append(
                EvidenceItem(
                    source=self.name,
                    finding=(
                        f"Internal Registry: Vendor '{vendor_name}' status is {registry_info.get('procurement_status', 'Unknown')}, "
                        f"security status: {registry_sec_status} (last review: {sec_review_date or 'none'}), "
                        f"legal terms: {legal_terms_status}."
                    ),
                    reference=f"data/vendors.csv:{registry_info.get('vendor_id', '')}",
                )
            )

        if api_available and api_info:
            evidence_items.append(
                EvidenceItem(
                    source="vendor_risk_service",
                    finding=(
                        f"External Risk API: Risk level: {api_info.get('risk_level', 'unknown')}, "
                        f"security review status: {api_info.get('security_review_status', 'unknown')}, "
                        f"personal data: {processes_personal_data}, outside region: {stores_data_outside_region}."
                    ),
                    reference=f"api:/vendor-risk/{vendor_name}",
                )
            )
        else:
            evidence_items.append(
                EvidenceItem(
                    source="vendor_risk_service",
                    finding=f"External Risk API unavailable for '{vendor_name}'. Error: {api_error_detail}",
                    reference=f"api:/vendor-risk/{vendor_name}",
                )
            )

        if has_conflict:
            evidence_items.append(
                EvidenceItem(
                    source=self.name,
                    finding=f"Security conflict detected: registry marks '{vendor_name}' as Approved, but external risk API indicates '{effective_sec_status}'.",
                    reference="procurement_policy.md:Section 5",
                )
            )

        return {
            "vendor_name": vendor_name,
            "registry_info": registry_info,
            "api_info": api_info,
            "api_available": api_available,
            "api_error_detail": api_error_detail,
            "is_new_vendor": is_new_vendor,
            "is_expired": is_expired,
            "has_conflict": has_conflict,
            "security_status": effective_sec_status,
            "legal_terms_status": legal_terms_status,
            "processes_personal_data": processes_personal_data,
            "stores_data_outside_region": stores_data_outside_region,
            "evidence": evidence_items,
        }


class ProcurementPolicyCheckerTool:
    """Tool 4: Deterministic policy and approval rules evaluation engine."""

    name = "procurement_policy_engine"

    def execute(
        self,
        request: dict[str, Any],
        employee_info: dict[str, Any] | None,
        budget_info: dict[str, Any] | None,
        catalog_overlap_info: dict[str, Any] | None,
        vendor_info: dict[str, Any] | None,
        telemetry: RunTelemetryCounter | None = None,
    ) -> PolicyEvaluationResult:
        if telemetry:
            telemetry.record_tool_call(self.name)

        return evaluate_procurement_policy(
            request=request,
            employee_info=employee_info,
            budget_info=budget_info,
            catalog_overlap_info=catalog_overlap_info,
            vendor_info=vendor_info,
        )
