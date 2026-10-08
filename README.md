# AI Procurement Request Copilot

An enterprise-grade, evaluation-backed AI Procurement Request Copilot that ingests employee software and service requests, retrieves grounded facts using specialized tools, deterministically enforces financial and compliance policies in code, and synthesizes structured procurement decisions while strictly reserving sensitive approvals and exceptions for authorized humans.

---

## Problem

Modern organizations face escalating software sprawl, shadow IT, and compliance risks. Employees frequently request new SaaS subscriptions and tools without visibility into:
1. **Existing Catalog Overlap:** Redundant purchases of tools already licensed internally.
2. **Budget Ceilings:** Departmental software allocations and committed spend limits.
3. **Vendor Security & Privacy Exposure:** Unassessed third parties handling customer PII, source code, or production infrastructure.
4. **Complex Approval Hierarchies:** Multi-tier authorization rules spanning Managers, Department Heads, Finance, CFO, Security, Privacy, and Legal.
5. **Adversarial / Incomplete Requests:** Vague business justifications or deliberate attempts to bypass review through prompt injection.

Procurement teams need a copilot that accelerates review cycles without compromising financial or regulatory discipline.

---

## Solution

The **AI Procurement Request Copilot** bridges AI context reasoning with deterministic code-level enforcement:
- **AI for Context & Interpretation:** Parses nuances of business justifications, identifies potential gaps, and drafts next steps.
- **Code for Hard Rules & Math:** Deterministically evaluates budget arithmetic, approval tiers, vendor assessment expiration (365-day policy snapshot against reference date `2026-09-30`), and mandatory security/privacy/legal gating.
- **Human Authority for Sensitive Approvals:** AI never autonomously purchases, commits budget, or overrides policy; every request generates an advisory `ProcurementDecision` routed to required human approvers.

---

## Product Workflow

```text
               +--------------------------------------+
               | 1. Employee Purchase Request Ingest  |
               +------------------+-------------------+
                                  |
                                  v
               +--------------------------------------+
               | 2. Input Sanitation & Validation     |
               | (Prompt Injection & Completeness)    |
               +------------------+-------------------+
                                  |
                                  v
               +--------------------------------------+
               | 3. Tool-Based Evidence Gathering     |
               | - Employee Hierarchy & Dept Budget   |
               | - Software Catalog & Past Purchases  |
               | - Vendor Registry & Mock Risk API    |
               +------------------+-------------------+
                                  |
                                  v
               +--------------------------------------+
               | 4. Deterministic Policy Engine       |
               | - Financial Threshold Tier Mapping   |
               | - Budget Availability Verification   |
               | - Security, Privacy, Legal Gating    |
               +------------------+-------------------+
                                  |
                                  v
               +--------------------------------------+
               | 5. Contextual Decision Formulation   |
               | (Structured ProcurementDecision)     |
               +------------------+-------------------+
                                  |
                                  v
               +--------------------------------------+
               | 6. Human Approver Review Gate        |
               +--------------------------------------+
```

---

## Setup

### Prerequisites
- Python 3.11, 3.12, or 3.13
- Git

### 1. Environment Installation
Clone the repository and set up a virtual environment:

**macOS / Linux:**
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

**Windows PowerShell:**
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 2. Verify Pre-Flight Setup
Run the starter integrity check:
```bash
python verify_setup.py
```
Expected output: `PRE-FLIGHT PASSED`.

### 3. Optional Model Credentials
The system includes a built-in deterministic reasoning engine that operates offline without API keys. To enable live external LLM generation, copy `.env.example` to `.env` and configure your preferred provider:
```bash
cp .env.example .env
```
Supported variables: `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GOOGLE_API_KEY`, `GEMINI_API_KEY`, `MODEL_NAME`.

---

## One-Command Run

Launch both the mock vendor-risk microservice (`http://127.0.0.1:8001`) and the interactive Streamlit UI (`http://127.0.0.1:8501`) with a single command:

```bash
python run_local.py
```

Open your browser to `http://localhost:8501` to interact with the copilot.

---

## Data Sources

All business data is grounded in synthetic assessment records located in `data/`:
- `employees.csv`: Employee directory, manager reporting lines, levels, and countries.
- `department_budgets.csv`: Annual software budgets, committed spend, and net available funds (`available_usd = annual_software_budget_usd - committed_usd`).
- `software_catalog.csv`: Approved internal software licenses, seat counts, scope, and capabilities.
- `purchase_history.csv`: Historical POs, renewal dates, and contract values.
- `vendors.csv`: Internal procurement registry containing security review dates, status, and legal terms.
- `vendor_risk.json`: Backing dataset for the external mock risk API (`/vendor-risk/{vendor_name}`).
- `procurement_policy.md`: Source of truth policy guidelines (Snapshot reference date: **`2026-09-30`**).

---

## Tools

The system implements 4 modular tools equipped with `RunTelemetryCounter` observability:

1. **`EmployeeBudgetLookupTool` (`employee_budget_tool`):**
   - Retrieves requester details, manager name/ID, and department budget.
   - Calculates available budget and returns verified employee metadata.
2. **`SoftwareCatalogLookupTool` (`software_catalog_tool`):**
   - Cross-references request against `software_catalog.csv` and `purchase_history.csv`.
   - Identifies exact product duplicates and category-level alternatives to surface `existing_tool_overlap`.
3. **`VendorSecurityLookupTool` (`vendor_security_tool`):**
   - Queries internal registry (`vendors.csv`) and external mock risk API.
   - Validates security review recency against snapshot reference date `2026-09-30` (365-day limit).
   - Flags discrepancies (`conflicting_vendor_evidence`), expired reviews (`vendor_review_expired`), and catches API service outages (`vendor_risk_unavailable`) gracefully without fabricating safety.
4. **`ProcurementPolicyCheckerTool` (`procurement_policy_engine`):**
   - Deterministic engine evaluating approval tiers, budget sufficiency, and compliance requirements in pure code.

---

## Deterministic Policy Engine

Implemented in `src/policy_engine.py` directly from `data/procurement_policy.md`:
- **Financial Thresholds:**
  - $\le \$1,000$: Manager
  - $\$1,000.01 - \$10,000$: Department Head + Procurement
  - $\$10,000.01 - \$25,000$: Department Head + Finance + Procurement
  - $> \$25,000$: Department Head + Finance + CFO + Procurement
- **Budget Gating:**
  - If `annual_cost_usd > available_usd`, flags `budget_insufficient` and routes to Finance for exception review.
- **Security Review Gating:**
  - Triggered by source code access, production/cloud integrations, confidential documents, employee/customer PII, unapproved/expired vendor review, or vendor API failure. Flags `security_review_required`.
- **Privacy Review Gating:**
  - Triggered by employee/customer PII, vendor personal data processing, or cross-border data storage. Flags `privacy_review_required`.
- **Legal Review Gating:**
  - Triggered by new vendors with spend $\ge \$10,000$, non-standard legal terms, or cross-region issues. Flags `legal_review_required`.

---

## Architecture A - Single Agent

- **Design:** Single end-to-end `SingleProcurementAgent`.
- **Execution Flow:**
  1. Gathers context across all 3 lookup tools.
  2. Executes `ProcurementPolicyCheckerTool`.
  3. Synthesizes findings, builds grounded evidence items, and formulates structured recommendation.
- **Attributes:** Low latency, single LLM call (or 0 in deterministic offline mode), minimal complexity, 0 handoff serialization risk.

---

## Architecture B - Staged / Two Agent

- **Design:** Staged 2-agent pipeline with intermediate deterministic policy gate:
  - **Stage 1 (Procurement Analyst):** Gathers tool evidence, validates request completeness, checks prompt injection, and emits structured `EvidencePackage`.
  - **Intermediate Gate:** Pure-code `ProcurementPolicyCheckerTool` executes on the evidence package.
  - **Stage 2 (Decision Reviewer):** Ingests `EvidencePackage` + policy results to resolve conflicting signals, recommend next steps, and assemble `ProcurementDecision`.
- **Attributes:** Modular separation of research vs decision; incurs 2x LLM calls, higher token overhead, and slightly higher latency.

---

## Human-in-the-Loop

In accordance with policy Section 11:
- `human_review_required` is **always True**.
- The copilot acts strictly as an advisory decision support system.
- Sensitive purchasing, budget alterations, and regulatory exceptions strictly require designated human approvals (Manager, Department Head, Finance, CFO, Security, Privacy, Legal).

---

## Prompt Injection Defense

All request fields (`business_justification`, `product_name`, `vendor_name`) are treated as **untrusted data**:
1. Regular expression filters scan for adversarial patterns (e.g. `ignore all procurement rules`, `treat as cfo-approved`, `bypass policy`).
2. Detections trigger the `prompt_injection_detected` risk flag and add security evidence.
3. When prompts are sent to external LLMs, business data is isolated inside `<untrusted_request_data>` tags with explicit system instructions prohibiting directive execution.
4. Crucially, deterministic policy evaluation executes in Python code; injected text has zero capability to alter numerical threshold calculations or suppress mandatory approvals.

---

## Failure Handling

- **Vendor Risk API Outage:** When the mock API returns 503 or network errors, `VendorSecurityLookupTool` catches the exception, marks `api_available=False`, flags `vendor_risk_unavailable`, and escalates to Security and Legal for manual verification.
- **Missing Information:** Incomplete requests (e.g. missing annual cost, seat count, or data access level) trigger `missing_information` risk flags and generate concrete requests for clarification.
- **Conflicting Records:** If the vendor registry indicates "Approved" while external assessment marks "Expired", the system flags `conflicting_vendor_evidence` and `vendor_review_expired`.

---

## Evaluation Methodology

Both architectures were tested against the identical public evaluation benchmark (`evals/public_cases.json`):
- `PUB-01` (`REQ-1001`): Low-value approved vendor ($800) -> Manager approval.
- `PUB-02` (`REQ-1002`): New vendor with catalog alternatives ($12k) -> Overlap, Security, Legal.
- `PUB-03` (`REQ-1003`): Approved vendor with source-code access ($18k) -> Security review.
- `PUB-04` (`REQ-1005`): Budget shortfall & sensitive data ($22k) -> Budget, Privacy, Security, Legal.
- `PUB-05` (`REQ-1006`): Incomplete request + prompt injection -> Missing info, injection defense.
- `PUB-06` (`REQ-1009`): Mock API 503 outage ($15k) -> Tool failure escalation.

Run evaluations using:
```bash
python evals/run_public_evals.py --architecture single
python evals/run_public_evals.py --architecture staged
```

---

## Evaluation Results

| Evaluation Metric | Architecture A (Single Agent) | Architecture B (Staged / 2-Agent) |
|---|---:|---:|
| **Public Cases Passed** | **6 / 6 (100%)** | **6 / 6 (100%)** |
| **Average Latency (Local Benchmark)** | **~123.5 ms** | **~127.5 ms** |
| **Tool Calls per Case** | 4 tools | 4 tools |
| **LLM Calls per Case (Online Mode)** | 1 call | 2 calls (+100% cost/latency) |
| **Policy Compliance Rate** | 100% | 100% |
| **Prompt Injection Neutralization** | 100% (Flagged) | 100% (Flagged) |
| **API Failure Graceful Handling** | 100% (Escalated) | 100% (Escalated) |

Detailed CSV reports are exported to `evals/results_single.csv` and `evals/results_staged.csv`.

---

## Architecture Comparison

| Dimension | Architecture A (Single Agent) | Architecture B (Staged Two-Agent) |
|---|---|---|
| **Simplicity & Maintainability** | High; single cohesive pipeline | Moderate; multi-stage handoff contracts |
| **Cost & Latency** | Low; single LLM call, ~123 ms | Higher; 2x LLM calls, additional serialization |
| **Grounding Quality** | Flawless; grounded via tools & policy engine | Flawless; uses identical tools & policy engine |
| **Marginal Accuracy Gain** | Baseline | **0% marginal gain** over Architecture A |

---

## Final Ship Decision

**Recommendation:** Ship **Architecture A (Single Agent)**.

**Rationale:**
Because deterministic compliance rules (budget math, threshold approvals, PII triggers, API outage handling) are implemented in pure Python, splitting the workflow into two agents provides zero marginal improvement in accuracy, grounding, or safety. Architecture B doubles LLM inference cost, introduces latency overhead, and increases maintenance surface area without client benefit. Architecture A is lean, robust, and production-ready.

---

## Assumptions

1. **Policy Reference Date:** Date calculations evaluate against **2026-09-30** as defined in `data/procurement_policy.md`.
2. **Assessment Expiration:** Vendor security reviews are valid for 365 calendar days from their recorded review date.
3. **Net Available Budget:** `available_usd = annual_software_budget_usd - committed_usd`.
4. **Advisory Copilot:** All decisions require designated human approval prior to financial commitment.

---

## Known Limitations

1. **Keyword Overlap Detection:** Software catalog matching relies on category and keyword heuristics; high-volume production should add dense vector embeddings for fuzzy semantic match.
2. **Static Budget Snapshot:** Assumes budget data is read-only; production deployment requires transactional locks with ERP systems (NetSuite, Workday).
3. **Prompt Injection Boundary:** Regex heuristics provide defense-in-depth, but production deployments should incorporate specialized safety guardrail classifiers (e.g., Llama Guard).

---

## Project Structure

```text
.
├── .env.example                     # Environment template for optional LLM keys
├── .gitignore                       # Clean Git exclusion rules (no keys, venvs, caches)
├── README.md                        # Complete project documentation & guide
├── STUDENT_CHECKLIST.md             # Verification checklist against brief
├── app.py                           # Interactive Streamlit copilot UI dashboard
├── run_local.py                     # One-command launcher (FastAPI API + UI)
├── verify_setup.py                  # Starter pack pre-flight check
├── requirements.txt                 # Python package dependencies
├── data/                            # Synthetic enterprise datasets & policy
│   ├── department_budgets.csv
│   ├── employees.csv
│   ├── procurement_policy.md        # Source of truth policy
│   ├── purchase_history.csv
│   ├── requests.json                # 10 synthetic purchase requests
│   ├── software_catalog.csv
│   ├── vendor_risk.json             # Backing data for mock API
│   └── vendors.csv
├── docs/
│   └── Assignment_3_Brief.pdf       # Client challenge specification
├── evals/                           # Evaluation harness & results
│   ├── public_cases.json            # 6 public test cases
│   ├── results_single.csv           # Benchmark results for Architecture A
│   ├── results_staged.csv           # Benchmark results for Architecture B
│   └── run_public_evals.py          # Reproducible evaluation runner
├── mock_api/                        # Mock external vendor-risk FastAPI service
│   └── app.py
├── src/                             # Core application logic
│   ├── __init__.py
│   ├── agents.py                    # SingleAgent & StagedTwoAgent implementations
│   ├── contracts.py                 # ProcurementDecision & EvidenceItem Pydantic schemas
│   ├── data_access.py               # Data loaders
│   ├── policy_engine.py             # Deterministic procurement policy rules & thresholds
│   ├── solution.py                  # Assessment adapter (handle_request)
│   ├── telemetry.py                 # Telemetry & call counters
│   ├── tools.py                     # 4 observable tools (Employee, Catalog, Vendor, Policy)
│   └── vendor_client.py             # Vendor risk API client with fallback
├── templates/
│   ├── architecture_decision.md     # Architecture decision memo (<= 500 words)
│   └── workflow_notes.md            # Architecture diagrams & design notes
└── tests/                           # Unit and integration test suite
    ├── test_data_integrity.py       # Starter dataset integrity tests
    ├── test_mock_api.py             # Mock API tests
    ├── test_policy_engine.py        # Policy engine & threshold unit tests
    ├── test_solution.py             # Solution adapter integration tests
    └── test_tools.py                # 4-tool test suite
```
