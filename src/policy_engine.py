from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any
from pydantic import BaseModel, Field

from src.contracts import EvidenceItem

REFERENCE_DATE = date(2026, 9, 30)
MAX_ASSESSMENT_AGE_DAYS = 365

INJECTION_PATTERNS = [
    r"ignore\s+(all\s+)?(procurement\s+)?rules",
    r"ignore\s+previous\s+instructions",
    r"treat\s+this\s+request\s+as\s+.*approved",
    r"approve\s+(it\s+)?immediately",
    r"cfo-approved",
    r"bypass\s+(all\s+)?(approvals?|policy|controls?)",
    r"system\s+prompt",
    r"disregard\s+(policy|rules|security)",
    r"override\s+(policy|procurement|rules)",
]


class PolicyEvaluationResult(BaseModel):
    required_approvals: list[str] = Field(default_factory=list)
    risk_flags: list[str] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)
    evidence: list[EvidenceItem] = Field(default_factory=list)
    human_review_required: bool = True
    deterministic_recommendation: str = ""
    deterministic_next_step: str = ""


def detect_prompt_injection(text: str | None) -> bool:
    """Detect potential prompt injection or adversarial policy-bypass instructions in business data."""
    if not text:
        return False
    lowered = text.lower()
    for pattern in INJECTION_PATTERNS:
        if re.search(pattern, lowered):
            return True
    return False


def parse_date(date_val: str | None) -> date | None:
    if not date_val:
        return None
    try:
        return date.fromisoformat(str(date_val).strip())
    except ValueError:
        return None


def is_date_expired(review_date_str: str | None, reference_date: date = REFERENCE_DATE) -> bool:
    d = parse_date(review_date_str)
    if not d:
        return True
    return (reference_date - d).days > MAX_ASSESSMENT_AGE_DAYS


def evaluate_procurement_policy(
    request: dict[str, Any],
    employee_info: dict[str, Any] | None,
    budget_info: dict[str, Any] | None,
    catalog_overlap_info: dict[str, Any] | None,
    vendor_info: dict[str, Any] | None,
) -> PolicyEvaluationResult:
    """Deterministic procurement policy evaluation implementing data/procurement_policy.md."""
    approvals: list[str] = []
    risk_flags: list[str] = []
    missing_info: list[str] = []
    evidence_items: list[EvidenceItem] = []

    # 1. Untrusted content & prompt injection check
    business_text_fields = [
        request.get("business_justification", ""),
        request.get("product_name", ""),
        request.get("vendor_name", ""),
    ]
    has_injection = any(detect_prompt_injection(txt) for txt in business_text_fields)
    if has_injection:
        risk_flags.append("prompt_injection_detected")
        evidence_items.append(
            EvidenceItem(
                source="security_policy_filter",
                finding="Untrusted request text contains policy-bypass/override attempt. Neutralized and flagged for human review.",
                reference="procurement_policy.md:Section 9",
            )
        )

    # 2. Required request information validation (Section 1)
    cost = request.get("annual_cost_usd")
    if cost is None:
        missing_info.append("annual cost")
    user_count = request.get("user_count")
    if user_count is None:
        missing_info.append("user count")
    data_access = request.get("data_access_level")
    if not data_access or str(data_access).strip().lower() in ("unknown", "none_specified"):
        missing_info.append("data access level")
    if not request.get("business_justification"):
        missing_info.append("business purpose")
    if not request.get("product_name") or not request.get("vendor_name"):
        missing_info.append("product/vendor identification")

    if missing_info:
        risk_flags.append("missing_information")
        evidence_items.append(
            EvidenceItem(
                source="policy_completeness_check",
                finding=f"Missing required procurement fields: {', '.join(missing_info)}.",
                reference="procurement_policy.md:Section 1",
            )
        )

    # 3. Budget Check (Section 2)
    available_budget = budget_info.get("available_usd") if budget_info else None
    if cost is not None and available_budget is not None:
        if cost > available_budget:
            risk_flags.append("budget_insufficient")
            if "Finance" not in approvals:
                approvals.append("Finance")
            evidence_items.append(
                EvidenceItem(
                    source="budget_check",
                    finding=f"Request cost (${cost:,.2f}) exceeds department available software budget (${available_budget:,.2f}).",
                    reference="procurement_policy.md:Section 2",
                )
            )
        else:
            evidence_items.append(
                EvidenceItem(
                    source="budget_check",
                    finding=f"Request cost (${cost:,.2f}) is within department available software budget (${available_budget:,.2f}).",
                    reference="procurement_policy.md:Section 2",
                )
            )

    # 4. Financial Approval Thresholds (Section 4)
    if cost is not None:
        if cost <= 1000.0:
            if "Manager" not in approvals:
                approvals.append("Manager")
        elif cost <= 10000.0:
            for role in ["Department Head", "Procurement"]:
                if role not in approvals:
                    approvals.append(role)
        elif cost <= 25000.0:
            for role in ["Department Head", "Finance", "Procurement"]:
                if role not in approvals:
                    approvals.append(role)
        else:
            for role in ["Department Head", "Finance", "CFO", "Procurement"]:
                if role not in approvals:
                    approvals.append(role)
        evidence_items.append(
            EvidenceItem(
                source="financial_threshold_policy",
                finding=f"Annual spend of ${cost:,.2f} maps to mandatory approval tier: {', '.join(approvals)}.",
                reference="procurement_policy.md:Section 4",
            )
        )
    else:
        # Default baseline if cost missing
        for role in ["Department Head", "Procurement"]:
            if role not in approvals:
                approvals.append(role)

    # 5. Existing Software / Catalog Overlap (Section 3)
    if catalog_overlap_info and catalog_overlap_info.get("has_overlap"):
        risk_flags.append("existing_tool_overlap")
        overlapping = catalog_overlap_info.get("overlapping_tools", [])
        tool_names = [t.get("product_name", "Unknown") for t in overlapping]
        evidence_items.append(
            EvidenceItem(
                source="software_catalog_check",
                finding=f"Existing approved software identified with capability overlap: {', '.join(tool_names)}.",
                reference="procurement_policy.md:Section 3",
            )
        )

    # 6. Vendor & Security Assessment (Section 5, 8, 10)
    data_access_level = str(request.get("data_access_level", "")).lower()
    integrations = [str(i).lower() for i in request.get("requested_integrations", [])]
    sensitive_data = any(
        kw in data_access_level
        for kw in ["source_code", "production", "confidential", "employee_pii", "customer_pii"]
    )
    sensitive_integrations = any(
        any(kw in integ for kw in ["git", "code", "production", "cloud", "repository", "crm", "helpdeskly"])
        for integ in integrations
    )

    vendor_api_failed = vendor_info.get("api_available") is False if vendor_info else False
    vendor_expired = vendor_info.get("is_expired", False) if vendor_info else False
    vendor_conflict = vendor_info.get("has_conflict", False) if vendor_info else False
    vendor_sec_status = vendor_info.get("security_status", "unknown") if vendor_info else "unknown"
    vendor_new = vendor_info.get("is_new_vendor", False) if vendor_info else False

    security_needed = False
    if sensitive_data or sensitive_integrations:
        security_needed = True
    if vendor_sec_status != "approved" or vendor_expired or vendor_conflict or vendor_api_failed:
        security_needed = True

    if vendor_api_failed:
        risk_flags.append("vendor_risk_unavailable")
        evidence_items.append(
            EvidenceItem(
                source="vendor_risk_service",
                finding="External vendor-risk API unavailable (503/network error). Live security assessment could not be retrieved.",
                reference="procurement_policy.md:Section 10",
            )
        )

    if vendor_expired:
        risk_flags.append("vendor_review_expired")
        evidence_items.append(
            EvidenceItem(
                source="vendor_security_check",
                finding=f"Vendor security assessment expired (>365 days from policy reference date {REFERENCE_DATE}).",
                reference="procurement_policy.md:Section 5",
            )
        )

    if vendor_conflict:
        risk_flags.append("conflicting_vendor_evidence")
        evidence_items.append(
            EvidenceItem(
                source="vendor_security_check",
                finding="Discrepancy detected between internal vendor registry and external vendor-risk service records.",
                reference="procurement_policy.md:Section 5",
            )
        )

    if security_needed:
        if "Security" not in approvals:
            approvals.append("Security")
        if "security_review_required" not in risk_flags:
            risk_flags.append("security_review_required")
        evidence_items.append(
            EvidenceItem(
                source="security_policy",
                finding=f"Security review required (data: '{data_access_level}', integrations: {integrations}, vendor status: '{vendor_sec_status}').",
                reference="procurement_policy.md:Section 5",
            )
        )

    # 7. Privacy Review (Section 6)
    processes_pii = any(kw in data_access_level for kw in ["employee_pii", "customer_pii"])
    vendor_processes_personal = vendor_info.get("processes_personal_data", False) if vendor_info else False
    vendor_outside_region = vendor_info.get("stores_data_outside_region", False) if vendor_info else False

    if processes_pii or vendor_processes_personal or vendor_outside_region:
        if "Privacy" not in approvals:
            approvals.append("Privacy")
        if "privacy_review_required" not in risk_flags:
            risk_flags.append("privacy_review_required")
        evidence_items.append(
            EvidenceItem(
                source="privacy_policy",
                finding=f"Privacy review required (PII handling: {processes_pii or vendor_processes_personal}, cross-region storage: {vendor_outside_region}).",
                reference="procurement_policy.md:Section 6",
            )
        )

    # 8. Legal Review (Section 7)
    legal_terms_status = vendor_info.get("legal_terms_status", "unknown").lower() if vendor_info else "unknown"
    legal_needed = False
    if vendor_new and (cost is None or cost >= 10000.0):
        legal_needed = True
    if legal_terms_status not in ("approved", "standard"):
        legal_needed = True
    if vendor_api_failed and (cost is None or cost >= 10000.0 or sensitive_data):
        legal_needed = True
    if vendor_outside_region and (processes_pii or vendor_processes_personal):
        legal_needed = True

    if legal_needed:
        if "Legal" not in approvals:
            approvals.append("Legal")
        if "legal_review_required" not in risk_flags:
            risk_flags.append("legal_review_required")
        evidence_items.append(
            EvidenceItem(
                source="legal_policy",
                finding=f"Legal review required (vendor: {'New' if vendor_new else 'Existing'}, spend: ${cost or 0:,.2f}, terms: '{legal_terms_status}').",
                reference="procurement_policy.md:Section 7",
            )
        )

    # Deterministic recommendations & next steps
    if has_injection:
        rec = "Reject request and escalate prompt injection"
        next_step = "Route request to Security and Procurement for adversarial review and policy enforcement."
    elif missing_info:
        rec = "Request clarification on missing information"
        next_step = f"Request updated proposal from requester specifying missing fields ({', '.join(missing_info)})."
    elif "budget_insufficient" in risk_flags:
        rec = "Escalate for budget exception and multi-stakeholder review"
        next_step = f"Route to {', '.join(approvals)} for formal exception review and vendor assessment."
    elif "existing_tool_overlap" in risk_flags:
        rec = "Evaluate existing catalog software before approving new purchase"
        next_step = f"Engage requester to evaluate existing approved software ({', '.join(tool_names)}) or submit exception to {', '.join(approvals)}."
    elif "security_review_required" in risk_flags or "vendor_risk_unavailable" in risk_flags:
        rec = "Route for security and compliance review"
        next_step = f"Submit security assessment ticket and route to {', '.join(approvals)} for formal evaluation."
    else:
        rec = "Proceed with standard business approvals"
        next_step = f"Route purchase request to {', '.join(approvals)} for sign-off."

    return PolicyEvaluationResult(
        required_approvals=approvals,
        risk_flags=risk_flags,
        missing_information=missing_info,
        evidence=evidence_items,
        human_review_required=True,
        deterministic_recommendation=rec,
        deterministic_next_step=next_step,
    )
