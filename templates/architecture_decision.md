# Architecture Decision Memo: AI Procurement Request Copilot

**Maximum length: 500 words**

## Decision
We recommend shipping **Architecture A (Single-Agent with Deterministic Policy Engine)** for production deployment.

## Evidence
Both architectures were evaluated against the identical public evaluation suite across six diverse procurement scenarios:

| Metric | Architecture A (Single Agent) | Architecture B (Staged / 2-Agent) |
|---|---:|---:|
| Evaluation Cases Passing (6/6) | 100% (6/6) | 100% (6/6) |
| Deterministic Policy Compliance | 100% | 100% |
| Prompt Injection Resistance | 100% (Flagged & Neutralized) | 100% (Flagged & Neutralized) |
| Tool Failure Handling (API Outage) | 100% (Safe Escalation) | 100% (Safe Escalation) |
| Average Latency (Local Benchmark) | ~123.5 ms | ~127.5 ms |
| LLM Calls per Request (Online Mode) | 1 call | 2 calls (+100% overhead) |
| Tool Invocations per Request | 4 tools | 4 tools |
| Qualitative Grounding Failures | 0 | 0 |

## Trade-offs
- **Single Agent (Architecture A):** Couples evidence retrieval, deterministic policy evaluation, and recommendation synthesis into a streamlined pipeline. It achieves 100% policy compliance, halves model token consumption, minimizes network roundtrips, and eliminates intermediate handoff serialization risks.
- **Staged / Two-Agent (Architecture B):** Separates the Analyst (researcher) from the Decision Reviewer via an intermediate structured evidence package. While conceptually modular, this orchestration introduces a 2x LLM invocation overhead, doubles token costs, and increases failure modes if the intermediate contract drifts. Because deterministic business rules (approval thresholds, budget ceilings, PII/security gating) are enforced in immutable Python code rather than model reasoning, the second agent provides zero marginal accuracy improvement on compliance or risk mitigation.

## Risks / Limitations
1. **Catalog Semantics:** Free-text semantic overlap is currently bounded by keyword and category matching; embedding-based semantic retrieval should be added before indexing thousands of SaaS tools.
2. **Dynamic Quotas:** Real-time budget commitments rely on snapshot snapshots; live ERP/NetSuite sync is required for high-frequency concurrent checkout.
3. **Model Provider Drift:** When online LLM synthesis is enabled, prompt injection defenses rely on rigid XML isolation; continuous automated adversarial red-teaming is essential.

## Why This is the Right MVP
The core challenge in procurement automation is not open-ended agentic autonomy—it is **reliable grounding, strict policy compliance, and predictable human handoff**.

By placing deterministic constraints (budget arithmetic, threshold tiers, regulatory triggers) in code and keeping final purchasing power strictly with authorized human managers, Architecture A satisfies all governance requirements with minimum complexity, lowest latency, and minimal operating expense. Unnecessary multi-agent orchestration adds cognitive and financial debt without measurable benefit. Therefore, Architecture A represents the superior engineering solution.
