# ALR-TW Open-Source Architecture Proposals (RFCs)

This directory contains five formal Open-Source RFC / Feature Proposals for
`LucasYeh702/alr-tw`. Proposals 01–04 were prepared from the perspective of an
external third-party contributor and system architect; proposal 05 records the
maintainer-approved v0.12 quick-research design.

These proposals strictly enforce the architectural **separation of concerns**:
- **The Data Layer (資料層)**: Private databases, citation graphs, scrapers, and embedding indexes remain external and deployer-owned.
- **The Harness Layer (鞍具層 / ALR-TW)**: Remains the neutral, deterministic, fail-closed verification engine.

---

## Index of Proposals

| # | Proposal Document | Target Area | Key Objective |
|---|---|---|---|
| **01** | [`01-rfc-pluggable-candidate-provider-protocols.md`](01-rfc-pluggable-candidate-provider-protocols.md) | Architecture / Decoupling | Decouple core harness from hardcoded TLR HTTP calls by defining `CandidateRecallProvider` and `LineageCandidateProvider` Protocols. |
| **02** | [`02-rfc-in-engine-autonomous-obligation-execution.md`](02-rfc-in-engine-autonomous-obligation-execution.md) | Protocol / Ergonomics | Reduce MCP tool-call multi-hop latency by adding an in-engine autonomous execution loop for server-owned obligations. |
| **03** | [`03-rfc-graduated-answer-posture-and-qualified-advisory.md`](03-rfc-graduated-answer-posture-and-qualified-advisory.md) | Contracts / Civil Law | Avoid total draft redaction under bounded counter-authority scope by introducing a `qualified_advisory` posture with mandatory structural caveat envelopes. |
| **04** | [`04-feature-official-cli-conformance-suite-for-data-providers.md`](04-feature-official-cli-conformance-suite-for-data-providers.md) | Tooling / Standards | Provide an official `alr-tw verify-provider` CLI tool so third parties can validate their local databases against harness contracts. |
| **05** | [`05-rfc-bounded-verified-quick-research.md`](05-rfc-bounded-verified-quick-research.md) | Research / Latency | Add prompt-selected, bounded quick judgment research while retaining exact official verification and final answer validation. |

## v0.12.0 disposition

| Proposal | Disposition in v0.12.0 |
|---|---|
| 01 | Core ports accepted: `CandidateRecallProvider` and `LineageCandidateProvider`; TLR remains the reference adapter and the v0.11 constructor slot remains compatible. A bundled local graph adapter is not claimed. |
| 02 | Accepted: `execute_run_to_completion` and MCP `execute_legal_research` perform bounded single-roundtrip server orchestration while preserving operation records. |
| 03 | Accepted as an adaptation: the existing `qualified` / `conditional` posture is reused instead of adding a synonymous enum. Verified subsets remain presentable only after answer validation and with mandatory qualifications. |
| 04 | Adapted: `alr-tw verify-provider --input <envelope.json>` checks caller-supplied structure and field relationships only. It does not certify source origin, trusted receipts, evidence promotion, or presentation. Direct recursive shard, FTS, or graph inspection is not shipped. |
| 05 | Accepted: prompt commands, maximum-five official checks, verified-subset qualification, evidence handoff, and elapsed-time telemetry. |

---

## Submission Guide for GitHub

To submit any of these proposals to the upstream GitHub repository using `gh` CLI:

```bash
# Submit RFC 01
gh issue create -R LucasYeh702/alr-tw \
  --title "[RFC] Decouple Core Harness from Hardcoded TLR Dependency via Pluggable CandidateProvider Protocols" \
  --label "enhancement" \
  --body-file 01-rfc-pluggable-candidate-provider-protocols.md

# Submit RFC 02
gh issue create -R LucasYeh702/alr-tw \
  --title "[RFC] In-Engine Autonomous Obligation Execution to Reduce MCP Multi-Hop Tool-Call Friction" \
  --label "enhancement" \
  --body-file 02-rfc-in-engine-autonomous-obligation-execution.md

# Submit RFC 03
gh issue create -R LucasYeh702/alr-tw \
  --title "[RFC] Refine ResearchSufficiency & AnswerMode: Introduce Qualified Advisory to Prevent Total Draft Redaction under Bounded Scope" \
  --label "enhancement" \
  --body-file 03-rfc-graduated-answer-posture-and-qualified-advisory.md

# Submit Feature 04
gh issue create -R LucasYeh702/alr-tw \
  --title "[Feature] Provide Official CLI Conformance Test Suite for External Data Providers" \
  --label "enhancement" \
  --body-file 04-feature-official-cli-conformance-suite-for-data-providers.md

# Submit RFC 05
gh issue create -R LucasYeh702/alr-tw \
  --title "[RFC] Bounded Verified Quick Research for Prompt-Selected Fast Case Retrieval" \
  --label "enhancement" \
  --body-file 05-rfc-bounded-verified-quick-research.md
```
