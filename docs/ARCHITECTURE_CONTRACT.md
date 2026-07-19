# Architecture Contract

## v0.6 server-owned contract

新整合應以 `alr_tw.contracts` 的 provider-neutral models、`ResearchService`、`ProviderObligationExecutor` 與 `SqliteStore` 為主。外部 agent 只能建立／推進 run 與提交 draft；不得提交 evidence span 讓 final validation 採信。

```text
ResearchRun -> ordered obligations -> ProviderResult
            -> SourceRecord -> EvidenceSpan
            -> server-owned final validation
```

`ProviderCandidate` 永遠不是 `EvidenceSpan`。官方即時內容只有在 provider 完成 origin、schema、content 與 freshness 檢查並由 server 儲存後，才能成為 `evidence_eligible`。Source identifier、hash、role 與 timestamp 不可由 MCP caller 自我認證。

v0.5 以前的 `tw_legal_rag_mcp.contracts` 仍為 legacy synthetic contract，相容期間不得與 v0.6 server-owned records 混作同一 authority store。

本文件說明使用者接入自己的法規、裁判、憲法法庭資料或其他合規資料源時，建議保留的資料流介面、來源驗證邊界與 trust gate 規則。本 repo 只示範可替換介面，不提供部署環境專屬的資料、索引、快取、切片策略、調校後的 production ranking 權重或私有評測集。

## Purpose

This contract helps implementers replace the synthetic demo with their own compliant data sources while keeping the same verification boundary.

使用者應能從這份文件看懂：資料如何進入 adapter，如何成為 retrieval candidate，如何經過 citation verification，最後如何由 trust gate 決定可回答或應拒答。

公開版不承諾任何特定資料集、硬體規格、向量資料庫、embedding 模型、chunking strategy 或調校後的 production ranking formula。repo 內含的 demo ranking formula 與通用預設只用來展示資料流與測試契約，不代表閉源 runtime 的實際配置。

## Contract Boundary

```text
source_manifest
-> adapter_result
-> retrieval_candidate
-> citation_verification
-> final_citations
-> trust_gate
-> answer_validation
```

這條邊界表示：上層 AI 不應直接讀取原始資料檔或未驗證檢索結果作答，而應透過可替換的 adapter / retriever / verifier 取得帶有來源狀態、引用資格與驗證結果的資料。

## Public Interfaces

| Interface | Location | Contract |
|---|---|---|
| `SourceManifest` | `src/tw_legal_rag_mcp/contracts.py` | Describes provider, dataset, version, source URL, licensing metadata, retrieval time, and source tier. |
| `AdapterResult` | `src/tw_legal_rag_mcp/contracts.py` | Represents adapter output plus its source manifest and ingestion status. |
| `RetrievalCandidate` | `src/tw_legal_rag_mcp/contracts.py` | Represents candidate recall output with citation metadata, source tier, score, and verification fields. |
| `SourceAdapter` | `src/tw_legal_rag_mcp/contracts.py` | Adapter protocol for source-specific ingestion. |
| `Retriever` | `src/tw_legal_rag_mcp/contracts.py` | Retriever protocol for query-to-candidate recall. |
| `CitationVerifier` | `src/tw_legal_rag_mcp/contracts.py` | Verifier protocol for source policy and final-citation eligibility checks. |
| `run_synthetic_contract_pipeline` | `src/tw_legal_rag_mcp/contracts.py` | Synthetic end-to-end contract demonstration without production data. |

## Trust Invariants

Production implementations should preserve these invariants even when replacing the synthetic adapter, retriever, index, or verifier:

1. Retrieval candidates are not final citations by default.
2. `external_semantic_recall` may improve recall, but it remains candidate-only unless separately verified through an official source or verified cache.
3. `staging` data must not enter a final citation index before official verification and promotion.
4. `synthetic` records are demo / test fixtures only and must never be treated as Taiwan law.
5. Final citations must come from `official` sources or qualifying `verified_cache` records with traceable official URL, content hash, and verification time.
6. Candidate-only, unknown, rejected, or unverifiable citations must not satisfy answer validation.
7. If no final citation remains after validation, the trust gate must fail closed.
8. Citation eligibility is separate from legal force. Production systems should separately model `legal_effect_type`, `normative_weight`, `citation_role`, or equivalent metadata.
9. Non-answer traces must not include directly presentable answer content.
10. Trace tool calls should identify whether they are deterministic harness records or actual live tool calls.

## Out Of Scope

This public contract intentionally excludes deployment-specific tuning and private operational assets, including:

- production legal datasets
- official full-text caches
- vector or FTS indexes
- chunk size and overlap
- embedding model and vector dimension
- HNSW or vector database parameters
- SQLite FTS settings
- tuned production ranking weights or production scoring formula
- private evaluation holdouts
- user query logs
- credentials, tokens, private endpoints, and local paths

These items are deployment concerns. Demo ranking formula examples in this repo, including RRF and source-tier scores, are illustrative and not production configuration. Production ranking settings should be selected by each implementer according to data source, hardware capacity, latency budget, update frequency, precision requirements, storage cost, and compliance policy.

## Extension Points

Implementers can replace or extend the following layers without changing the trust boundary:

- source adapters for statutes, judgments, Constitutional Court materials, administrative interpretations, or private legal-team data
- retrievers backed by SQLite FTS, vector stores, hybrid search, external semantic recall, or local-only indexes
- citation verifiers that re-check official URLs, recompute content hashes, handle tombstones, and apply freshness policies
- ranking layers that consider citation eligibility, source tier, legal effect, court level, date, and issue fit
- MCP tools or service APIs that expose search, exact lookup, citation validation, and trust gate results

TLR-like semantic indexes can be used as high-recall retrieval sources, but they
should feed candidate discovery only. For final citation eligibility, implementers
should verify candidates against original files downloaded from the Judicial Yuan
or another official source and promote only records with official URL or stable
identifier, content hash, download timestamp, and verification timestamp into a
local `verified_cache`.

## Contract Tests

`tests/integration/test_synthetic_contract_pipeline.py` validates the public contract with synthetic data:

1. The synthetic adapter, retriever, citation verifier, trust gate, and answer validation compose into a stable pipeline.
2. An `official` synthetic record can become a final citation.
3. An `external_semantic_recall` record remains candidate-only.
4. Candidate-only citations do not satisfy the trust gate when no final citation is present.
5. The public contract output does not expose production retrieval parameters such as chunk size, HNSW settings, ranking weights, or embedding model names.

These tests do not claim production retrieval quality. They only assert the architecture contract that a production implementation should preserve.
