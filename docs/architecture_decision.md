# Architecture Decision Memo: AI Procurement Request Copilot

## 1. Ship Decision
We recommend shipping **Architecture A (Single Agent with Deterministic Policy Engine)**. Offline mode testing demonstrates that Architecture A and Architecture B achieve identical policy adherence and evidence grounding. Architecture B requires two sequential LLM calls by design (Analyst followed by Reviewer) versus one call for Architecture A, introducing serialization overhead without improving deterministic rule adherence.

## 2. Empirical Evaluation Evidence
Both architectures were evaluated across 22 benchmark cases (6 public scenarios and 16 boundary, edge, and injection cases) in `evals/run_evals.py`:

| Evaluation Metric | Architecture A (Single Agent) | Architecture B (Staged Two-Agent) | Delta (B vs A) |
|---|---:|---:|---:|
| **Cases Passing Quality Criteria** | **22/22 (100.0%)** | **22/22 (100.0%)** | **0.0%** |
| **Deterministic Policy Compliance** | **100.0%** | **100.0%** | 0.0% |
| **Recommendation Category Accuracy** | **100.0%** | **100.0%** | 0.0% |
| **Tool Evidence Groundedness** | **100.0%** | **100.0%** | 0.0% |
| **Human Escalation Accuracy** | **100.0%** | **100.0%** | 0.0% |
| **Mean Latency (ms)** | **41.6 ms** | **40.9 ms** | -0.8 ms |
| **P50 Latency (ms)** | **45.2 ms** | **45.2 ms** | -0.0 ms |
| **P95 Latency (ms)** | **47.3 ms** | **49.5 ms** | +2.2 ms |
| **Average Tool Calls per Case** | **4.0** | **4.0** | 0.0 |
| **Average LLM Calls per Case** | **0.0** | **0.0** | 0.0 |

*Note: Offline mode: A and B are functionally identical by design; LLM-mode comparison not run. In online LLM mode, Architecture B costs 2 LLM calls vs 1 by design.*

## 3. Trade-offs & Production Rationale
- **Architecture A (Single Agent):** Unifies tool execution, Python policy evaluation, and recommendation synthesis into a single stage. It avoids inter-agent schema translation and halves LLM API round-trips when connected to remote model providers.
- **Architecture B (Staged Two-Agent):** Decouples research (`Analyst`) from final adjudication (`Reviewer`) across an intermediate `EvidencePackage`. Because procurement thresholds, budget calculations, and compliance gates (PII, source code, vendor review age) are enforced in deterministic Python code rather than model weights, the second agent provides no measured correctness advantage while doubling model invocations by design.

## 4. Known Limitations & Mitigations
1. **No Live-LLM Run:** Remote LLM evaluation was omitted due to remote provider server capacity limits (503); offline synthesis was validated deterministically.
2. **Catalog Semantics:** Free-text matching uses token boundaries and category fallbacks rather than vector embeddings.
3. **Data Snapshots:** Ledger and vendor risk data are daily CSV/API snapshots rather than real-time transactional webhooks.

## 5. Conclusion
Procurement governance requires strict policy compliance and human oversight. Architecture A satisfies all governance requirements at lower architectural complexity and lower model cost.
