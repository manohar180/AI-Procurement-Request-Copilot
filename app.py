from __future__ import annotations

import json
import time
from pathlib import Path

import streamlit as st

from src.contracts import ProcurementDecision
from src.data_access import load_budgets, load_employees
from src.solution import handle_request

ROOT = Path(__file__).resolve().parent
REQUESTS = json.loads((ROOT / "data" / "requests.json").read_text(encoding="utf-8"))
BY_ID = {r["request_id"]: r for r in REQUESTS}

EMPLOYEES = load_employees().set_index("employee_id").to_dict("index")
BUDGETS = load_budgets().set_index("department").to_dict("index")

st.set_page_config(
    page_title="AI Procurement Request Copilot",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("🛡️ AI Procurement Request Copilot")
st.caption(
    "Policy Reference Date: **2026-09-30** | Grounded Evidence Gathering • Deterministic Policy Enforcement • Human-in-the-Loop"
)

# ---------------- Sidebar Controls ----------------
st.sidebar.header("Controls & Configuration")

request_id = st.sidebar.selectbox(
    "Select Purchase Request",
    list(BY_ID.keys()),
    format_func=lambda rid: (
        f"{rid}: {BY_ID[rid]['product_name']} "
        f"(${BY_ID[rid]['annual_cost_usd']:,.0f})"
        if BY_ID[rid]["annual_cost_usd"] is not None
        else f"{rid}: {BY_ID[rid]['product_name']} (Cost Unknown)"
    ),
)

architecture = st.sidebar.radio(
    "Evaluation Architecture",
    options=["single", "staged"],
    format_func=lambda a: "Architecture A: Single Agent" if a == "single" else "Architecture B: Staged / Two Agent",
    index=0,
)

show_comparison = st.sidebar.checkbox("Compare Architectures Side-by-Side", value=False)

req = BY_ID[request_id]
requester = EMPLOYEES.get(req.get("requester_id", ""), {})
dept_name = requester.get("department", "Unknown")
dept_budget = BUDGETS.get(dept_name, {})

st.sidebar.divider()
st.sidebar.markdown(f"**Requester:** {requester.get('name', 'N/A')} ({requester.get('level', 'IC')})")
st.sidebar.markdown(f"**Department:** {dept_name}")
if dept_budget:
    st.sidebar.markdown(f"**Available Budget:** ${dept_budget.get('available_usd', 0):,.2f}")

st.sidebar.info(
    "🔒 **Human-in-the-Loop Principle**\n"
    "The AI Copilot synthesizes evidence and evaluates policy rules. Final approvals and spend commitments are strictly retained by authorized humans."
)

# ---------------- Helper Renderer ----------------
def render_decision_dashboard(decision: ProcurementDecision, latency_ms: float, title_suffix: str = ""):
    st.subheader(f"📋 Copilot Assessment {title_suffix}")

    # Top banner: Human Review Status & Recommendation
    col1, col2 = st.columns([1.5, 3.5])
    with col1:
        if decision.human_review_required:
            st.error("⚠️ **HUMAN REVIEW REQUIRED**\n\nAdvisory recommendation only.")
        else:
            st.success("✅ **Standard Processing**")
    with col2:
        st.info(f"**Recommendation:**\n\n{decision.recommendation}")

    # Next steps callout
    st.markdown(f"**👉 Next Action:** {decision.next_step}")

    # Approvals, Risk Flags, Missing Information in 3 columns
    c_app, c_risk, c_miss = st.columns(3)

    with c_app:
        st.markdown("#### ✍️ Required Approvals")
        if decision.required_approvals:
            for app in decision.required_approvals:
                st.markdown(f"- **{app}**")
        else:
            st.caption("No mandatory approvals identified.")

    with c_risk:
        st.markdown("#### 🚨 Policy & Risk Flags")
        if decision.risk_flags:
            for flag in decision.risk_flags:
                st.warning(f"`{flag}`")
        else:
            st.success("No risk flags raised.")

    with c_miss:
        st.markdown("#### ❓ Missing Information")
        if decision.missing_information:
            for m in decision.missing_information:
                st.error(f"Missing: **{m}**")
        else:
            st.success("All required fields provided.")

    # Grounded Evidence Panel
    st.markdown("#### 🔍 Grounded Tool Evidence")
    if decision.evidence:
        for idx, ev in enumerate(decision.evidence, 1):
            with st.expander(f"Evidence Item #{idx}: [{ev.source}]", expanded=(idx <= 2)):
                st.markdown(f"**Finding:** {ev.finding}")
                if ev.reference:
                    st.caption(f"📍 Reference: `{ev.reference}`")
    else:
        st.caption("No evidence items available.")

    # Telemetry and Execution Stats
    st.markdown("#### 📊 Observability & Telemetry")
    tel = decision.telemetry
    tcol1, tcol2, tcol3, tcol4 = st.columns(4)
    tcol1.metric("Latency", f"{latency_ms:.1f} ms")
    tcol2.metric("Tool Calls", tel.tool_calls if tel else 0)
    tcol3.metric("LLM Calls", tel.llm_calls if tel else 0)
    tcol4.metric("Tools Invoked", len(set(tel.tool_names)) if tel and tel.tool_names else 0)
    if tel and tel.tool_names:
        st.caption(f"Tools executed: `{', '.join(tel.tool_names)}`")


# ---------------- Layout Main ----------------
left_panel, right_panel = st.columns([1, 1.2], gap="large")

with left_panel:
    st.subheader("📥 Purchase Request Details")
    card_container = st.container(border=True)
    with card_container:
        st.markdown(f"### {req.get('product_name')} ({req.get('category')})")
        st.markdown(f"**Vendor:** {req.get('vendor_name')}")
        cost = req.get("annual_cost_usd")
        users = req.get("user_count")
        st.markdown(
            f"**Cost:** {f'${cost:,.2f}' if cost is not None else '*(Not Specified)*'} | "
            f"**Users/Seats:** {users if users is not None else '*(Not Specified)*'}"
        )
        st.markdown(f"**Data Access Level:** `{req.get('data_access_level', 'unknown')}`")
        st.markdown(f"**Integrations:** `{req.get('requested_integrations', [])}`")
        st.markdown(f"**Urgency:** `{req.get('urgency', 'normal')}`")
        st.markdown(f"**Business Justification:**\n> {req.get('business_justification')}")

    st.subheader("Raw Request Payload")
    st.json(req, expanded=False)

with right_panel:
    if not show_comparison:
        st.markdown(f"### Running Mode: `{architecture.upper()}`")
        if st.button("🚀 Analyze Request", type="primary", use_container_width=True):
            with st.spinner("Executing grounded tools and policy engine..."):
                t0 = time.perf_counter()
                decision = handle_request(request_id, architecture=architecture)
                dt = (time.perf_counter() - t0) * 1000
                render_decision_dashboard(decision, latency_ms=dt)
        else:
            st.info("Click **Analyze Request** to evaluate this procurement proposal.")
    else:
        st.markdown("### ⚖️ Side-by-Side Architecture Comparison")
        if st.button("🚀 Run Comparison", type="primary", use_container_width=True):
            tab_a, tab_b = st.tabs(["Architecture A (Single Agent)", "Architecture B (Staged Two-Agent)"])

            with tab_a:
                t0 = time.perf_counter()
                dec_a = handle_request(request_id, architecture="single")
                dt_a = (time.perf_counter() - t0) * 1000
                render_decision_dashboard(dec_a, latency_ms=dt_a, title_suffix="(Single Agent)")

            with tab_b:
                t0 = time.perf_counter()
                dec_b = handle_request(request_id, architecture="staged")
                dt_b = (time.perf_counter() - t0) * 1000
                render_decision_dashboard(dec_b, latency_ms=dt_b, title_suffix="(Staged / 2-Agent)")
        else:
            st.info("Click **Run Comparison** to execute both architectures against this request.")

st.divider()
st.caption(
    "FDE Assessment 3 | AI Procurement Request Copilot | "
    "Advisory system; sensitive purchasing approvals, budget modifications, and policy exceptions require designated human sign-off."
)
