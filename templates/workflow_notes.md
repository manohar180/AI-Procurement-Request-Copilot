# AI Procurement Request Copilot - Workflow & Architecture Notes

## 1. System Architectures

### Architecture A: Single-Agent Baseline
```text
               +----------------------------------+
               |     Purchase Request (Untrusted) |
               +-----------------+----------------+
                                 |
                                 v
               +----------------------------------+
               |    Single Procurement Agent      |
               +-----------------+----------------+
                                 |
     +---------------------------+---------------------------+
     |                           |                           |
     v                           v                           v
+----+----------------+ +--------+------------+ +------------+-------+
| Employee / Budget   | | Software Catalog    | | Vendor Security     |
| Lookup Tool         | | Overlap Tool        | | Lookup Tool         |
+----+----------------+ +--------+------------+ +------------+-------+
     |                           |                           |
     +---------------------------+---------------------------+
                                 |
                                 v
               +----------------------------------+
               | Deterministic Policy Engine Tool |
               | (Budget, Thresholds, Compliance) |
               +-----------------+----------------+
                                 |
                                 v
               +----------------------------------+
               | Grounded Evidence & Synthesis    |
               +-----------------+----------------+
                                 |
                                 v
               +----------------------------------+
               | Structured ProcurementDecision   |
               +-----------------+----------------+
                                 |
                                 v
               +----------------------------------+
               |   Human Approver Review Gate     |
               +-----------------+----------------+
```

### Architecture B: Staged / Two-Agent Variant
```text
               +----------------------------------+
               |     Purchase Request (Untrusted) |
               +-----------------+----------------+
                                 |
                                 v
               +----------------------------------+
               | Stage 1: Procurement Analyst     |
               | (Research & Grounding Agent)     |
               +-----------------+----------------+
                                 |
        +------------------------+------------------------+
        |                        |                        |
        v                        v                        v
+-------+--------------+ +-------+--------------+ +-------+--------------+
| Employee & Budget    | | Software Catalog     | | Vendor Security      |
| Lookup Tool          | | Overlap Tool         | | Lookup Tool          |
+-------+--------------+ +-------+--------------+ +-------+--------------+
        |                        |                        |
        +------------------------+------------------------+
                                 |
                                 v
               +----------------------------------+
               | Structured EvidencePackage       |
               +-----------------+----------------+
                                 |
                                 v
               +----------------------------------+
               | INTERMEDIATE DETERMINISTIC GATE  |
               | (Procurement Policy Engine Tool) |
               +-----------------+----------------+
                                 |
                                 v
               +----------------------------------+
               | Stage 2: Decision Reviewer Agent |
               | (Risk & Escalation Synthesizer)  |
               +-----------------+----------------+
                                 |
                                 v
               +----------------------------------+
               | Structured ProcurementDecision   |
               +-----------------+----------------+
                                 |
                                 v
               +----------------------------------+
               |   Human Approver Review Gate     |
               +-----------------+----------------+
```

---

## 2. Tools Architecture & Responsibilities

1. **`EmployeeBudgetLookupTool` (Deterministic):**
   - Retrieves employee record, reporting hierarchy (manager name/ID), and department budget.
   - Computes available vs. committed software budget without estimation error.
2. **`SoftwareCatalogLookupTool` (Heuristic/Catalog):**
   - Queries approved catalog (`software_catalog.csv`) and historical purchase records (`purchase_history.csv`).
   - Identifies product-level matches and category-level alternatives to prevent redundant procurement.
3. **`VendorSecurityLookupTool` (Hybrid Registry + Mock API):**
   - Retrieves internal vendor registry metadata (`vendors.csv`).
   - Calls live external mock risk API (`/vendor-risk/{vendor_name}`).
   - Catches service unavailability (503 / network drops) gracefully without fabricating safety.
   - Validates security assessment date against the reference date `2026-09-30` (365-day expiration threshold).
   - Flags discrepancies between internal registry and external assessment.
4. **`ProcurementPolicyCheckerTool` (Deterministic Engine):**
   - Hard-coded procurement policy engine mapping spend to approval tiers:
     - <= $1,000: Manager
     - $1,000.01 - $10,000: Department Head + Procurement
     - $10,000.01 - $25,000: Department Head + Finance + Procurement
     - > $25,000: Department Head + Finance + CFO + Procurement
   - Gating rules: Source code, production integrations, customer/employee PII, confidential documents, new vendors, and cross-region storage trigger mandatory Security, Privacy, and Legal approvals.

---

## 3. Separation of Concerns: AI vs Code vs Human

| Domain | Responsible Entity | Scope |
|---|---|---|
| **Deterministic Code** | Python Policy Engine | Numerical budget math, financial thresholds, date expiration comparisons, mandatory regulatory triggers, schema validation. |
| **Artificial Intelligence** | LLM / Synthesis Agent | Contextual interpretation of business justification, synthesizing evidence summaries, drafting advisory next steps. |
| **Human Authority** | Designated Human Approvers | Final spend commitment, policy exceptions, vendor contract execution, risk acceptance. |

---

## 4. Prompt Injection & Untrusted Data Defense

- All request fields (`business_justification`, `product_name`, `vendor_name`) are treated strictly as **untrusted data**.
- Regular expression heuristics flag explicit override attempts (`ignore rules`, `cfo-approved`, `bypass policy`).
- When prompt text is submitted to an LLM, it is isolated in explicit `<untrusted_request_data>` tags accompanied by strict system prompts prohibiting instruction execution from data blocks.
- Deterministic policy logic executes directly in Python; injected text cannot alter code-level calculation of approval tiers or risk flags.

---

## 5. What Was Intentionally Not Built

- **Autonomous Purchasing:** The copilot cannot execute transactions or modify budget spreadsheets autonomously.
- **Complex Multi-Agent Chains:** Restricted to a maximum of 2 agents to avoid circular delegations, cascading latency, and unpredictable state drift.
