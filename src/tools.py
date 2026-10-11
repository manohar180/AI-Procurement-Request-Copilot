from __future__ import annotations

import re
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
    parse_date,
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
                        finding=f"Requester ID '{requester_id}' not found in employee directory.",
                        reference="data/employees.csv",
                    )
                ],
            }

        emp = emp_row.iloc[0].to_dict()
        manager_id = emp.get("manager_id")
        manager_name = "None (Executive/VP)"
        if manager_id and str(manager_id).lower() not in ("none", "nan", ""):
            mgr_row = employees_df[employees_df["employee_id"] == manager_id]
            if not mgr_row.empty:
                manager_name = f"{mgr_row.iloc[0]['name']} ({manager_id})"

        dept = str(emp.get("department", ""))
        dept_budget_row = budgets_df[budgets_df["department"] == dept]
        budget_info: dict[str, Any] = {}
        if not dept_budget_row.empty:
            budget_info = dept_budget_row.iloc[0].to_dict()
            available = budget_info.get("available_usd") or 0
            annual = budget_info.get("annual_software_budget_usd") or 0
            committed = budget_info.get("committed_usd") or 0
            budget_finding = (
                f"Department: {dept} (Annual Budget: ${annual:,.2f}, "
                f"Committed: ${committed:,.2f}, Available: ${available:,.2f})."
            )
        else:
            budget_finding = f"Department '{dept}' not found in budget database."

        emp_finding = (
            f"Requester: {emp['name']} ({emp.get('level', 'IC')}, {emp.get('country', '')}), "
            f"Department: {dept}, Manager: {manager_name}. {budget_finding}"
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
        user_count: int | None = None,
        telemetry: RunTelemetryCounter | None = None,
    ) -> dict[str, Any]:
        if telemetry:
            telemetry.record_tool_call(self.name)

        if not product_name or not str(product_name).strip():
            return {
                "has_overlap": False,
                "is_expansion": False,
                "overlapping_tools": [],
                "evidence": [
                    EvidenceItem(
                        source=self.name,
                        finding="Cannot check catalog overlap: product name is missing from request.",
                        reference="data/software_catalog.csv",
                    )
                ],
            }

        catalog_df = load_software_catalog()
        purchases_df = load_purchase_history()

        prod_norm = str(product_name).lower().strip()
        cat_norm = str(category).lower().strip()
        ven_norm = str(vendor_name).lower().strip()

        # Check if the request is an add-on or license expansion of an already approved tool
        is_expansion_kw = bool(
            re.search(r"\b(add[_\s-]?on|expansion|training\s+pack|additional\s+seats?|extra\s+seats?)\b", prod_norm)
        )

        exact_matches = []
        category_matches = []
        vendor_matches = []

        for _, row in catalog_df.iterrows():
            item = row.to_dict()
            name_curr = str(item.get("product_name", "")).lower().strip()
            cat_curr = str(item.get("category", "")).lower().strip()
            ven_curr = str(item.get("vendor_name", "")).lower().strip()

            if prod_norm == name_curr:
                exact_matches.append(item)
            elif ven_norm and ven_norm == ven_curr:
                vendor_matches.append(item)
            elif cat_norm and cat_norm == cat_curr:
                category_matches.append(item)

        # Look up purchase history
        related_purchases = []
        for _, row in purchases_df.iterrows():
            p = row.to_dict()
            p_prod = str(p.get("product_name", "")).lower().strip()
            p_ven = str(p.get("vendor_name", "")).lower().strip()
            if prod_norm == p_prod or (ven_norm and ven_norm == p_ven):
                related_purchases.append(p)

        evidence_items: list[EvidenceItem] = []
        is_expansion = False
        has_overlap = False
        overlapping_tools: list[dict] = []

        # 1. If it's a true add-on/expansion for an approved existing vendor/tool:
        if (vendor_matches or exact_matches) and is_expansion_kw:
            is_expansion = True
            base_tool = (exact_matches or vendor_matches)[0]
            evidence_items.append(
                EvidenceItem(
                    source=self.name,
                    finding=(
                        f"Request is an expansion/add-on for existing approved catalog software: "
                        f"{base_tool['product_name']} ({base_tool['software_id']}, Scope: {base_tool.get('scope', 'Company-wide')}, "
                        f"Licensed seats: {base_tool.get('licensed_seats', 'N/A')}). Not a competing overlap."
                    ),
                    reference=f"data/software_catalog.csv:{base_tool['software_id']}",
                )
            )
            overlapping_tools = [base_tool]
        elif any(str(item.get("scope", "")).lower() == "company-wide" and cat_norm == str(item.get("category", "")).lower() for item in (exact_matches + vendor_matches + category_matches)):
            # Company-wide catalog tool already deployed in same category (e.g. TaskFlow Pro when TaskFlow exists)
            has_overlap = True
            cw_matches = [
                item for item in (exact_matches + vendor_matches + category_matches)
                if str(item.get("scope", "")).lower() == "company-wide" and cat_norm == str(item.get("category", "")).lower()
            ]
            m = cw_matches[0]
            seats_str = f"{m.get('licensed_seats')} licensed seats" if m.get("licensed_seats") else "active license"
            req_seats = f"{user_count} seats" if user_count is not None else "requested deployment"
            evidence_items.append(
                EvidenceItem(
                    source=self.name,
                    finding=(
                        f"Existing company-wide software '{m['product_name']}' ({m['software_id']}, {seats_str}) "
                        f"already active in category '{m.get('category')}'. Requested {req_seats} should be reviewed for "
                        f"unused company-wide capacity or credible gap documented per policy §3."
                    ),
                    reference=f"data/software_catalog.csv:{m['software_id']}",
                )
            )
            overlapping_tools = cw_matches
        elif exact_matches:
            # Exact duplicate of existing tool
            has_overlap = True
            m = exact_matches[0]
            evidence_items.append(
                EvidenceItem(
                    source=self.name,
                    finding=(
                        f"Exact product match already active in software catalog: {m['product_name']} "
                        f"({m['software_id']}, Status: {m.get('status')}, Scope: {m.get('scope')}, Licensed: {m.get('licensed_seats')} seats). "
                        "Evaluate if existing deployment satisfies need."
                    ),
                    reference=f"data/software_catalog.csv:{m['software_id']}",
                )
            )
            overlapping_tools = exact_matches
        elif category_matches:
            # Approved alternatives in same category
            has_overlap = True
            cat_tool_names = [
                f"{m['product_name']} ({m['software_id']}, Scope: {m.get('scope', '')})"
                for m in category_matches
            ]
            evidence_items.append(
                EvidenceItem(
                    source=self.name,
                    finding=f"Existing approved software identified in category '{category}': {', '.join(cat_tool_names)}. Potential overlap.",
                    reference=f"data/software_catalog.csv:{','.join(m['software_id'] for m in category_matches)}",
                )
            )
            overlapping_tools = category_matches
        elif vendor_matches:
            # Same vendor, different product
            v = vendor_matches[0]
            evidence_items.append(
                EvidenceItem(
                    source=self.name,
                    finding=f"Vendor '{vendor_name}' already supplies approved catalog software: {v['product_name']} ({v['software_id']}).",
                    reference=f"data/software_catalog.csv:{v['software_id']}",
                )
            )
            overlapping_tools = vendor_matches
        else:
            evidence_items.append(
                EvidenceItem(
                    source=self.name,
                    finding=f"No existing product or category match found in software catalog for '{product_name}' ({category}).",
                    reference="data/software_catalog.csv",
                )
            )

        if related_purchases:
            hist_str = ", ".join(
                f"{p['purchase_id']} (${p['annual_amount_usd']:,.2f} on {p['purchase_date']})"
                for p in related_purchases
            )
            evidence_items.append(
                EvidenceItem(
                    source=self.name,
                    finding=f"Prior purchase history found for vendor/product: {hist_str}.",
                    reference=f"data/purchase_history.csv:{related_purchases[0]['purchase_id']}",
                )
            )

        return {
            "has_overlap": has_overlap,
            "is_expansion": is_expansion,
            "exact_matches": exact_matches,
            "category_matches": category_matches,
            "overlapping_tools": overlapping_tools,
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
        vendor_clean = str(vendor_name or "").strip()
        vendor_row = vendors_df[vendors_df["vendor_name"].str.lower() == vendor_clean.lower()]

        registry_info: dict[str, Any] = {}
        is_new_vendor = True
        sec_review_date = None
        legal_terms_status = "Unknown"
        registry_sec_status = "Unknown"

        if not vendor_row.empty:
            registry_info = vendor_row.iloc[0].to_dict()
            is_new_vendor = str(registry_info.get("procurement_status", "")).lower() == "new"
            raw_date = registry_info.get("security_review_date")
            sec_review_date = raw_date if raw_date and str(raw_date).lower() not in ("none", "nan", "") else None
            legal_terms_status = str(registry_info.get("legal_terms_status", "Unknown"))
            registry_sec_status = str(registry_info.get("security_status", "Unknown"))

        # Query mock external service via vendor_client
        api_info: dict[str, Any] | None = None
        api_available = True
        api_error_detail: str | None = None
        api_status = "ok"

        try:
            api_info = get_vendor_risk(vendor_clean)
        except requests.HTTPError as e:
            msg = str(e)
            if "404" in msg:
                api_status = "not_found"
                api_error_detail = "Vendor not found in external vendor-risk database (404)."
            else:
                api_available = False
                api_status = "unavailable"
                api_error_detail = msg
        except requests.RequestException as e:
            api_available = False
            api_status = "unavailable"
            api_error_detail = str(e)
        except Exception as e:
            api_available = False
            api_status = "unavailable"
            api_error_detail = str(e)

        # Check dates, expiration, and conflicts
        api_review_date = None
        api_sec_status = "unknown"
        processes_personal_data = False
        stores_data_outside_region = False

        if api_available and api_info:
            api_sec_status = str(api_info.get("security_review_status", "unknown")).lower()
            raw_api_date = api_info.get("last_review_date")
            api_review_date = raw_api_date if raw_api_date and str(raw_api_date).lower() not in ("none", "nan", "") else None
            processes_personal_data = bool(api_info.get("processes_personal_data", False))
            stores_data_outside_region = bool(api_info.get("stores_data_outside_region", False))

        # Effective security status and review date
        effective_sec_status = registry_sec_status.lower()
        if api_available and api_info and api_sec_status != "unknown":
            effective_sec_status = api_sec_status

        effective_review_date = api_review_date or sec_review_date

        # Expiration logic: ONLY expired if a real date exists and is older than 365 days
        is_expired = False
        if effective_review_date:
            is_expired = is_date_expired(str(effective_review_date), reference_date=REFERENCE_DATE)
        if api_sec_status == "expired":
            is_expired = True

        # Conflict detection
        has_conflict = False
        if api_available and api_info:
            reg_status_clean = registry_sec_status.lower()
            # 1. Registry says Approved, but API says expired or not_completed
            if reg_status_clean == "approved" and api_sec_status in ("expired", "not_completed"):
                has_conflict = True
            # 2. Registry says Approved, but review date is expired
            if reg_status_clean == "approved" and is_expired:
                has_conflict = True
            # 3. Registry says Pending/New, but API says approved
            if reg_status_clean in ("pending", "new") and api_sec_status == "approved":
                has_conflict = True
            # 4. Dates differ significantly
            if sec_review_date and api_review_date and sec_review_date != api_review_date:
                has_conflict = True

        evidence_items: list[EvidenceItem] = []

        if registry_info:
            evidence_items.append(
                EvidenceItem(
                    source=self.name,
                    finding=(
                        f"Internal Registry: Vendor '{vendor_clean}' status: {registry_info.get('procurement_status', 'Unknown')}, "
                        f"security: {registry_sec_status} (last review: {sec_review_date or 'none'}), "
                        f"legal terms: {legal_terms_status}."
                    ),
                    reference=f"data/vendors.csv:{registry_info.get('vendor_id', '')}",
                )
            )

        if not api_available:
            evidence_items.append(
                EvidenceItem(
                    source="vendor_risk_service",
                    finding=f"External vendor-risk API unavailable for '{vendor_clean}'. Error: {api_error_detail}. Live security status could not be verified.",
                    reference=f"api:/vendor-risk/{vendor_clean}",
                )
            )
        elif api_status == "not_found":
            evidence_items.append(
                EvidenceItem(
                    source="vendor_risk_service",
                    finding=f"Vendor '{vendor_clean}' not found in external vendor-risk database (404). Security assessment missing.",
                    reference=f"api:/vendor-risk/{vendor_clean}",
                )
            )
        elif api_info:
            evidence_items.append(
                EvidenceItem(
                    source="vendor_risk_service",
                    finding=(
                        f"External Risk API: Risk level: {api_info.get('risk_level', 'unknown')}, "
                        f"security review status: {api_info.get('security_review_status', 'unknown')} "
                        f"(last review: {api_review_date or 'none'}), personal data: {processes_personal_data}, "
                        f"stores outside region: {stores_data_outside_region}."
                    ),
                    reference=f"api:/vendor-risk/{vendor_clean}",
                )
            )

        if has_conflict:
            evidence_items.append(
                EvidenceItem(
                    source=self.name,
                    finding=(
                        f"Conflicting vendor records detected: registry status '{registry_sec_status}' (date: {sec_review_date or 'none'}) "
                        f"vs API status '{api_sec_status}' (date: {api_review_date or 'none'}). Escalate to Security."
                    ),
                    reference="procurement_policy.md:Section 5",
                )
            )

        return {
            "vendor_name": vendor_clean,
            "registry_info": registry_info,
            "api_info": api_info,
            "api_available": api_available,
            "api_status": api_status,
            "api_error_detail": api_error_detail,
            "is_new_vendor": is_new_vendor,
            "is_expired": is_expired,
            "has_conflict": has_conflict,
            "security_status": effective_sec_status,
            "effective_review_date": effective_review_date,
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
