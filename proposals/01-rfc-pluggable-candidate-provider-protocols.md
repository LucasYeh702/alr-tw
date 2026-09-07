---
title: "[RFC] Decouple Core Harness from Hardcoded TLR Dependency via Pluggable CandidateProvider Protocols"
labels: ["enhancement", "architecture", "rfc"]
state: "draft"
author: "Third-Party Contributor / System Architect"
target_repo: "LucasYeh702/alr-tw"
---

# [RFC] Decouple Core Harness from Hardcoded TLR Dependency via Pluggable CandidateProvider Protocols

## 1. Summary
This RFC proposes formalizing the separation between the **Verification Harness Layer** and the **Recall / Candidate Discovery Data Layer** in `alr-tw`.

Currently, while the architecture documentation declares the project to be *agent-neutral* and *provider-neutral*, the implementation in `src/alr_tw/research/provider_executor.py` and `src/alr_tw/research/judgment_lineage.py` directly hardcodes dependencies on `self.providers.tlr`, `TLR_LINEAGE_PROVIDER_UNAVAILABLE`, and configuration settings like `ALR_TW_TLR_BASE_URL`.

We propose defining explicit, pluggable Python Protocols in `alr_tw.contracts.providers` for:
1. `CandidateRecallProvider` (semantic search / keyword retrieval)
2. `LineageCandidateProvider` (appellate and procedural history candidate discovery)

Under this design, `TLRProvider` becomes a first-party reference adapter conforming to these protocols, allowing deployers and enterprises to inject their own private retrieval backends (e.g. self-hosted Elasticsearch, Qdrant, LanceDB, or local SQLite Citation Graphs) as first-class citizens.

---

## 2. Motivation & Problem Statement

### 2.1 The Architectural Contract vs. Implementation Gap
`README.zh-TW.md` and `ARCHITECTURE.md` emphasize that ALR-TW is a **verification harness and deterministic safety gate**, NOT a monolithic legal database or search engine. The data layer is intended to be optional and interchangeable.

However, in the v0.11.0 runtime:
- In `src/alr_tw/research/provider_executor.py` (lines 207-208):
  ```python
  if self.providers.tlr is None:
      return self._lineage_blocked(normalized_jid, "TLR_LINEAGE_PROVIDER_UNAVAILABLE")
  ```
- In `src/alr_tw/research/provider_executor.py` (lines 220-225):
  `self._fetch_lineage_history()` directly invokes `self.providers.tlr.fetch_case_history()`.
- In `src/alr_tw/config/settings.py`, `tlr_base_url` and `tlr_api_key` are core fields on `Settings`.

### 2.2 Impact on Private Deployments & Data Sovereignty
When deploying ALR-TW in enterprise, law firm, or air-gapped intranet environments:
- Deployers who possess on-premise judicial databases (e.g., 30-year fulltext shards or graph databases) cannot wire their internal recall services into the research state machine.
- Air-gapped or offline runs cannot execute `inspect_judgment_lineage` even if local appellate graph tables exist, because the harness treats the absence of the remote TLR HTTP client as a fatal blocker.

---

## 3. Proposed Specification

### 3.1 Protocol Definitions in `alr_tw.contracts.providers`

Define runtime-checkable protocols for candidate discovery:

```python
from typing import Protocol, runtime_checkable, Sequence, Any
from alr_tw.contracts.sources import SourceRecord
from alr_tw.providers.tlr import TlrCaseHistoryRecord, PublicLawCandidate

@runtime_checkable
class CandidateRecallProvider(Protocol):
    \"\"\"Abstract protocol for candidate-only semantic / lexical discovery.\"\"\"

    provider_id: str

    def recall_candidates(
        self,
        query: str,
        *,
        limit: int = 10,
        filters: dict[str, Any] | None = None,
    ) -> Sequence[Any]:
        ...

@runtime_checkable
class LineageCandidateProvider(Protocol):
    \"\"\"Abstract protocol for discovering upper / lower appellate candidates.\"\"\"

    provider_id: str

    def fetch_case_history(
        self,
        root_canonical_jid: str,
        *,
        max_candidates: int = 8,
    ) -> TlrCaseHistoryRecord | None:
        \"\"\"Return candidate upper/lower case history entries for official verification.\"\"\"
        ...
```

### 3.2 Decoupling `ProviderSet` and `ProviderObligationExecutor`
Refactor `ProviderSet`:
```python
@dataclass(frozen=True)
class ProviderSet:
    laws: OfficialLawProvider
    judgments: Any
    tlr: CandidateRecallProvider | None = None
    lineage_candidates: LineageCandidateProvider | None = None
    constitutional: Any | None = None
```

In `ProviderObligationExecutor.inspect_judgment_lineage`:
- Query `self.providers.lineage_candidates` (or fallback to `self.providers.tlr`).
- Return a standardized error `LINEAGE_CANDIDATE_PROVIDER_UNAVAILABLE` instead of vendor-specific `TLR_LINEAGE_PROVIDER_UNAVAILABLE`.

### 3.3 Reference Adapters
1. **`TLRLineageAdapter`**: Wraps the existing `https://tlr.dr-lawbot.com` HTTP client.
2. **`LocalGraphLineageAdapter`**: An optional reference implementation querying local SQLite graph tables (e.g. `appellate_edges` where `from_jid = ?`).

---

## 4. Safety & Invariant Analysis
- **Zero Hallucination Preserved**: Decoupling the candidate provider does **NOT** weaken the verification boundary. All records returned by `LineageCandidateProvider` remain `evidence_eligible=False`.
- The existing official verification step (`OfficialJudgmentProvider` fulltext check + SHA-256 digest + disposition classification) remains 100% mandatory before any candidate is promoted to `verified_cache` or `official` evidence.
- Maintains strict conformance with `AuthorityLineageContract`.

---

## 5. Alternatives Considered
- **Keep TLR hardcoded and force clients to use `client_assisted` mode**:
  - *Drawback*: Requires the external LLM client to manually manage and submit candidate locators via multi-hop MCP calls, increasing latency, token consumption, and failure rates.
- **Merge fulltext search into the official judgment provider**:
  - *Drawback*: Violates the core separation of concerns between fast/fuzzy semantic recall and byte-exact authoritative verification.
