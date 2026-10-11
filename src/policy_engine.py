from __future__ import annotations

import re
import unicodedata
from datetime import date
from typing import Any
from pydantic import BaseModel, Field

from src.contracts import EvidenceItem

REFERENCE_DATE = date(2026, 9, 30)
MAX_ASSESSMENT_AGE_DAYS = 365

INJECTION_PATTERNS = [
    r"\b(ignore|forget|disregard|skip|bypass|waive|omit)\b.*\b(rules|instructions|guidelines|policy|controls|checks|reviews?|approvals?|directions)\b",
    r"\b(pre[-_\s]?authorized|pre[-_\s]?approved|already[-_\s]?approved)(\s+by\s+[a-zA-Z_\s-]+)?\b",
    r"\bno\s+need\s+for\s+(review|approval|security|checks|oversight)\b",
    r"\b(skip|waive|omit)\s+(review|approval|security|checks|policy)\b",
    r"\bdisregard\s+(prior|previous|above|all)?\s*(directions|instructions|rules|guidelines|policy)\b",
    r"\b(i\s+order\s+you|you\s+must\s+approve|mark\s+(it\s+|this\s+)?approved)\b",
    r"\bas\s+the\s+(ceo|cfo|director|vp|head\s+of\s+\w+)\b",
    r"\b(cfo[-_\s]?approved|treat\s+this\s+request\s+as\s+.*approved)\b",
    r"\b(approve\s+(it|this)?\s*immediately|auto[-_\s]?approve)\b",
    r"\b(system\s+prompt|developer\s+mode|jailbreak|reveal\s+.*prompt)\b",
    r"\b(override\s+(policy|procurement|rules|controls))\b",
]

SENSITIVE_DATA_KEYWORDS = {
    "source_code",
    "production_telemetry",
    "confidential_documents",
    "employee_pii",
    "customer_pii",
    "credentials",
    "secrets",
    "api_keys",
    "tokens",
    "password",
    "passwords",
}

SENSITIVE_DATA_TOKENS = {
    "source", "code", "source_code",
    "production", "telemetry", "production_telemetry",
    "confidential", "confidential_documents",
    "pii", "employee_pii", "customer_pii",
    "credentials", "credential",
    "secrets", "secret",
    "keys", "key", "api_keys", "apikey", "apikeys",
    "tokens", "token",
    "password", "passwords",
}

SENSITIVE_INTEGRATION_TOKENS = {
    "git", "github", "gitlab", "bitbucket",
    "repository", "repositories", "repo", "repos",
    "production", "cloud", "aws", "gcp", "azure",
}


class PolicyEvaluationResult(BaseModel):
    required_approvals: list[str] = Field(default_factory=list)
    risk_flags: list[str] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)
    evidence: list[EvidenceItem] = Field(default_factory=list)
    human_review_required: bool = True
    review_level: str = "business_approval"
    recommendation_category: str = "proceed"
    deterministic_recommendation: str = ""
    deterministic_next_step: str = ""


def _normalize_text(text: str | None) -> str:
    if not text:
        return ""
    normalized = unicodedata.normalize("NFKD", str(text))
    return re.sub(r"\s+", " ", normalized).strip().lower()


def _tokenize_string(val: str | None) -> set[str]:
    if not val:
        return set()
    cleaned = _normalize_text(val)
    parts = re.split(r"[_\s\-/,\.;:]+", cleaned)
    return {p.strip() for p in parts if p.strip()}


def detect_prompt_injection(text: str | None) -> bool:
    """Detect prompt injection or adversarial policy-override directives in text."""
    if not text:
        return False
    cleaned = _normalize_text(text)
    for pattern in INJECTION_PATTERNS:
        if re.search(pattern, cleaned):
            return True
    return False


def parse_date(date_val: str | None) -> date | None:
    if not date_val:
        return None
    try:
        clean = str(date_val).strip()
        if clean.lower() in ("nan", "none", "null", ""):
            return None
        return date.fromisoformat(clean)
    except (ValueError, TypeError):
        return None


def is_date_expired(review_date_str: str | None, reference_date: date = REFERENCE_DATE) -> bool:
    """Check if review date is older than 365 days from reference date.
    
    Returns False if date is missing/None (missing is not expired; it is not completed).
    Exactly 365 days is considered current per policy §5.
    """
    d = parse_date(review_date_str)
    if not d:
        return False
    return (reference_date - d).days > MAX_ASSESSMENT_AGE_DAYS


def _has_sensitive_data_access(data_access_level: str) -> tuple[bool, list[str]]:
    tokens = _tokenize_string(data_access_level)
    matched = list(tokens.intersection(SENSITIVE_DATA_TOKENS))
    # Also check full string normalized against keywords
    norm = _normalize_text(data_access_level).replace(" ", "_")
    for kw in SENSITIVE_DATA_KEYWORDS:
        if kw == norm and kw not in matched:
            matched.append(kw)
    return bool(matched), sorted(matched)


def _has_sensitive_integrations(integrations: list[str]) -> tuple[bool, list[str]]:
    matched = []
    for item in integrations:
        tokens = _tokenize_string(item)
        if tokens.intersection(SENSITIVE_INTEGRATION_TOKENS):
            matched.append(item)
    return bool(matched), matched


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

    # 1. Untrusted content & prompt injection scanning across all available business text
    business_text_sources = [
        ("request.business_justification", request.get("business_justification")),
        ("request.product_name", request.get("product_name")),
        ("request.vendor_name", request.get("vendor_name")),
        ("request.vendor_notes", request.get("vendor_notes")),
        ("request.api_notes", request.get("api_notes")),
    ]
    if vendor_info:
        if vendor_info.get("registry_info"):
            business_text_sources.append(("vendor.registry_notes", vendor_info["registry_info"].get("notes")))
        if vendor_info.get("api_info"):
            business_text_sources.append(("vendor.api_notes", vendor_info["api_info"].get("notes")))
        if vendor_info.get("api_error_detail"):
            business_text_sources.append(("vendor.api_error", vendor_info.get("api_error_detail")))

    injection_findings = []
    for source_label, text in business_text_sources:
        if text and detect_prompt_injection(str(text)):
            injection_findings.append((source_label, str(text)))

    has_injection = bool(injection_findings)
    if has_injection:
        risk_flags.append("prompt_injection_detected")
        src_labels = ", ".join(s for s, _ in injection_findings)
        evidence_items.append(
            EvidenceItem(
                source="security_policy_filter",
                finding=f"Prompt injection / policy bypass attempt detected in business text ({src_labels}). Injected directive neutralized; evaluating actual procurement policy per policy §9.",
                reference="procurement_policy.md:Section 9",
            )
        )
        if "Security" not in approvals:
            approvals.append("Security")
        if "security_review_required" not in risk_flags:
            risk_flags.append("security_review_required")

    # 2. Required request information validation (Policy §1)
    cost = request.get("annual_cost_usd")
    if cost is None:
        missing_info.append("annual cost")
    user_count = request.get("user_count")
    if user_count is None:
        missing_info.append("user count")
    data_access = request.get("data_access_level")
    norm_data_access = _normalize_text(data_access)
    if not data_access or norm_data_access in ("unknown", "none_specified", "unspecified", ""):
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

    # 3. Budget Check (Policy §2)
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

    # 4. Financial Approval Thresholds (Policy §4)
    # Grounding statement must accurately list only the threshold tier's own minimum approvals
    tier_approvals: list[str] = []
    if cost is not None:
        if cost <= 1000.0:
            tier_approvals = ["Manager"]
        elif cost <= 10000.0:
            tier_approvals = ["Department Head", "Procurement"]
        elif cost <= 25000.0:
            tier_approvals = ["Department Head", "Finance", "Procurement"]
        else:
            tier_approvals = ["Department Head", "Finance", "CFO", "Procurement"]

        for role in tier_approvals:
            if role not in approvals:
                approvals.append(role)

        evidence_items.append(
            EvidenceItem(
                source="financial_threshold_policy",
                finding=f"Annual spend of ${cost:,.2f} maps to financial threshold tier requiring: {', '.join(tier_approvals)} per policy §4.",
                reference="procurement_policy.md:Section 4",
            )
        )
    else:
        # Cost is missing: baseline business review pending cost determination
        tier_approvals = ["Department Head", "Procurement"]
        for role in tier_approvals:
            if role not in approvals:
                approvals.append(role)

    # 5. Existing Software / Catalog Overlap (Policy §3)
    is_expansion = False
    if catalog_overlap_info:
        is_expansion = catalog_overlap_info.get("is_expansion", False)
        has_overlap = catalog_overlap_info.get("has_overlap", False)

        if is_expansion:
            tool_names = [t.get("product_name", "Unknown") for t in catalog_overlap_info.get("overlapping_tools", [])]
            evidence_items.append(
                EvidenceItem(
                    source="software_catalog_check",
                    finding=f"Request is an expansion/add-on extending existing approved catalog item(s): {', '.join(tool_names)}.",
                    reference="procurement_policy.md:Section 3",
                )
            )
        elif has_overlap:
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

    # 6. Vendor & Security Assessment (Policy §5, §8, §10)
    data_access_level = str(request.get("data_access_level", ""))
    integrations = request.get("requested_integrations", [])
    has_sens_data, sens_data_types = _has_sensitive_data_access(data_access_level)
    has_sens_int, sens_int_types = _has_sensitive_integrations(integrations)

    vendor_api_failed = vendor_info.get("api_available") is False if vendor_info else False
    vendor_expired = vendor_info.get("is_expired", False) if vendor_info else False
    vendor_conflict = vendor_info.get("has_conflict", False) if vendor_info else False
    vendor_sec_status = str(vendor_info.get("security_status", "unknown")).lower() if vendor_info else "unknown"
    vendor_new = vendor_info.get("is_new_vendor", False) if vendor_info else False
    review_date_val = vendor_info.get("effective_review_date") if vendor_info else None

    security_needed = False
    sec_reasons = []

    if has_sens_data:
        security_needed = True
        sec_reasons.append(f"sensitive data access ({', '.join(sens_data_types)})")
    if has_sens_int:
        security_needed = True
        sec_reasons.append(f"infrastructure integration ({', '.join(sens_int_types)})")

    if vendor_api_failed:
        security_needed = True
        risk_flags.append("vendor_risk_unavailable")
        evidence_items.append(
            EvidenceItem(
                source="vendor_risk_service",
                finding="External vendor-risk API unavailable (503/network error). Live security posture could not be verified.",
                reference="procurement_policy.md:Section 10",
            )
        )
        sec_reasons.append("vendor-risk service outage")

    if vendor_expired:
        security_needed = True
        risk_flags.append("vendor_review_expired")
        evidence_items.append(
            EvidenceItem(
                source="vendor_security_check",
                finding=f"Vendor security assessment expired (>365 days from policy reference date {REFERENCE_DATE}).",
                reference="procurement_policy.md:Section 5",
            )
        )
        sec_reasons.append("expired security assessment")
    elif not vendor_api_failed and (vendor_sec_status in ("not_completed", "pending", "unknown") or review_date_val is None):
        if vendor_new or vendor_sec_status != "approved":
            security_needed = True
            sec_reasons.append(f"vendor security assessment not completed ({vendor_sec_status})")
            evidence_items.append(
                EvidenceItem(
                    source="vendor_security_check",
                    finding=f"Vendor security assessment is not completed (status: '{vendor_sec_status}', review date: {review_date_val or 'none'}).",
                    reference="procurement_policy.md:Section 5",
                )
            )

    if vendor_conflict:
        security_needed = True
        risk_flags.append("conflicting_vendor_evidence")
        evidence_items.append(
            EvidenceItem(
                source="vendor_security_check",
                finding="Discrepancy detected between internal vendor registry and external vendor-risk service records.",
                reference="procurement_policy.md:Section 5",
            )
        )
        sec_reasons.append("conflicting vendor evidence")

    if security_needed:
        if "Security" not in approvals:
            approvals.append("Security")
        if "security_review_required" not in risk_flags:
            risk_flags.append("security_review_required")
        evidence_items.append(
            EvidenceItem(
                source="security_policy",
                finding=f"Security review required per policy §5 due to: {'; '.join(sec_reasons)}.",
                reference="procurement_policy.md:Section 5",
            )
        )

    # 7. Privacy Review (Policy §6)
    # Triggered ONLY when tool processes employee/customer PII or sensitive data stored outside region
    has_pii = any(k in sens_data_types for k in ["employee_pii", "customer_pii"])
    vendor_outside_region = vendor_info.get("stores_data_outside_region", False) if vendor_info else False
    vendor_processes_personal = vendor_info.get("processes_personal_data", False) if vendor_info else False

    privacy_needed = False
    privacy_reasons = []

    if has_pii:
        privacy_needed = True
        privacy_reasons.append("processes employee or customer PII")
    if vendor_outside_region and (has_pii or has_sens_data):
        privacy_needed = True
        privacy_reasons.append("sensitive data stored outside operating region")

    if privacy_needed:
        if "Privacy" not in approvals:
            approvals.append("Privacy")
        if "privacy_review_required" not in risk_flags:
            risk_flags.append("privacy_review_required")
        evidence_items.append(
            EvidenceItem(
                source="privacy_policy",
                finding=f"Privacy review required per policy §6 ({'; '.join(privacy_reasons)}).",
                reference="procurement_policy.md:Section 6",
            )
        )
    elif vendor_processes_personal:
        evidence_items.append(
            EvidenceItem(
                source="privacy_policy",
                finding="Vendor risk record indicates personal data capability, but requested scope does not process PII.",
                reference="procurement_policy.md:Section 6",
            )
        )

    # 8. Legal Review (Policy §7)
    legal_terms_status = str(vendor_info.get("legal_terms_status", "unknown")).lower() if vendor_info else "unknown"
    legal_needed = False
    legal_reasons = []

    if vendor_new and (cost is None or cost >= 10000.0):
        legal_needed = True
        legal_reasons.append(f"new vendor with annual spend >= $10,000 (${cost or 0:,.2f})")
    if legal_terms_status not in ("approved", "standard"):
        legal_needed = True
        legal_reasons.append(f"vendor legal terms status is '{legal_terms_status}' (not approved)")
    if vendor_api_failed and (cost is None or cost >= 10000.0 or has_sens_data):
        legal_needed = True
        legal_reasons.append("vendor risk assessment unavailable for material/sensitive purchase")
    if vendor_outside_region and has_pii:
        legal_needed = True
        legal_reasons.append("cross-border data processing terms require legal review")

    if legal_needed:
        if "Legal" not in approvals:
            approvals.append("Legal")
        if "legal_review_required" not in risk_flags:
            risk_flags.append("legal_review_required")
        evidence_items.append(
            EvidenceItem(
                source="legal_policy",
                finding=f"Legal review required per policy §7 ({'; '.join(legal_reasons)}).",
                reference="procurement_policy.md:Section 7",
            )
        )

    # 9. AI Tools Rules (Policy §8)
    cat_norm = _normalize_text(request.get("category", ""))
    prod_norm = _normalize_text(request.get("product_name", ""))
    is_ai_request = "ai" in cat_norm or "ai" in prod_norm or "neural" in prod_norm or "codemate" in prod_norm
    if is_ai_request and has_sens_data:
        evidence_items.append(
            EvidenceItem(
                source="ai_procurement_policy",
                finding=f"AI product requested for sensitive data ({', '.join(sens_data_types)}). Prior vendor approval does not authorize sensitive data access; Security and Privacy review enforced per policy §8.",
                reference="procurement_policy.md:Section 8",
            )
        )

    # 10. Review Level Classification
    if any(f in risk_flags for f in ("budget_insufficient", "vendor_risk_unavailable", "prompt_injection_detected", "conflicting_vendor_evidence")):
        review_level = "escalation"
    elif any(f in risk_flags for f in ("security_review_required", "privacy_review_required", "legal_review_required")):
        review_level = "specialist_review"
    elif any(a in approvals for a in ("Department Head", "Procurement")):
        review_level = "business_approval"
    else:
        review_level = "manager_sign_off"

    # 11. Deterministic Recommendation & Next Step Synthesis (Prioritized & Combined)
    if missing_info:
        rec = f"Request clarification on missing information ({', '.join(missing_info)})"
        next_step = f"Ask requester to clarify missing fields ({', '.join(missing_info)}) before routing to {', '.join(approvals)}."
    elif "budget_insufficient" in risk_flags:
        specialists = [a for a in ["Security", "Privacy", "Legal"] if a in approvals]
        if specialists:
            rec = f"Escalate for budget exception and specialist review ({', '.join(specialists)})"
            next_step = f"Route to Finance for budget exception and {', '.join(specialists)} for compliance sign-off."
        else:
            rec = "Escalate for budget exception review with Finance"
            next_step = f"Route to Finance and {', '.join(approvals)} for budget exception approval."
    elif "vendor_risk_unavailable" in risk_flags:
        rec = "Escalate to Security and Legal due to vendor-risk service outage"
        next_step = f"Submit manual vendor risk assessment and route to {', '.join(approvals)}."
    elif "conflicting_vendor_evidence" in risk_flags:
        rec = "Escalate to Security for vendor record reconciliation"
        next_step = f"Reconcile conflicting vendor records with Security before routing to {', '.join(approvals)}."
    elif any(f in risk_flags for f in ("security_review_required", "privacy_review_required", "legal_review_required")):
        specialists = [a for a in ["Security", "Privacy", "Legal"] if a in approvals]
        if "existing_tool_overlap" in risk_flags:
            rec = f"Evaluate existing catalog alternatives and route for specialist review ({', '.join(specialists)})"
            next_step = f"Engage requester on existing alternatives and route to {', '.join(approvals)} for review."
        else:
            rec = f"Route for specialist compliance reviews ({', '.join(specialists)})"
            next_step = f"Submit compliance review tickets and route to {', '.join(approvals)}."
    elif "existing_tool_overlap" in risk_flags:
        overlapping_tools = catalog_overlap_info.get("overlapping_tools", []) if catalog_overlap_info else []
        tool_names = [t.get("product_name", "Unknown") for t in overlapping_tools]
        rec = f"Evaluate existing catalog software ({', '.join(tool_names)}) before approving new purchase"
        next_step = f"Engage requester to evaluate existing catalog software ({', '.join(tool_names)}) or submit exception to {', '.join(approvals)}."
    else:
        # Standard low-risk case
        if approvals == ["Manager"]:
            rec = "Proceed with manager approval"
            next_step = "Route purchase request to Manager for standard approval."
        else:
            rec = f"Proceed with business approvals ({', '.join(approvals)})"
            next_step = f"Route purchase request to {', '.join(approvals)} for standard sign-off."

    if has_injection:
        rec += " (prompt injection flagged for security review)"
        next_step += " Alert Security of detected prompt injection directive."

    if "prompt_injection_detected" in risk_flags or "budget_insufficient" in risk_flags or "vendor_risk_unavailable" in risk_flags:
        recommendation_category = "escalate"
    elif missing_info:
        recommendation_category = "clarify"
    elif "existing_tool_overlap" in risk_flags:
        recommendation_category = "evaluate_alternatives"
    elif any(f in risk_flags for f in ("security_review_required", "privacy_review_required", "legal_review_required", "vendor_review_expired", "conflicting_vendor_evidence")):
        recommendation_category = "specialist_review"
    else:
        recommendation_category = "proceed"

    return PolicyEvaluationResult(
        required_approvals=approvals,
        risk_flags=risk_flags,
        missing_information=missing_info,
        evidence=evidence_items,
        human_review_required=True,
        review_level=review_level,
        recommendation_category=recommendation_category,
        deterministic_recommendation=rec,
        deterministic_next_step=next_step,
    )
