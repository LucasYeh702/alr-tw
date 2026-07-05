# Data Policy

本文件定義公開 reference repo 的資料邊界、來源信任分級與正式環境導入原則。

## Scope

本 repo 公開的是台灣法律 RAG / MCP 系統的參考框架：工具介面、source trust policy、citation validation、trust gate、synthetic demo 與可替換的資料流介面。

本 repo 不內建 production legal datasets，也不替使用者下載或重散布官方全文資料。使用者應依自己的資料來源、硬體效能、部署成本、精度需求與合規政策，自行建置資料、索引、快取與參數設定。

## Source tiers

| Tier | 說明 | 可作 final citation |
|---|---|---|
| official | 官方來源，例如法務部、司法院、憲法法庭、主管機關網站或 API | Yes |
| verified_cache | 已回官方來源核對，具 official URL / hash / verified_at 的本地快取 | Conditional |
| staging | HF 或其他外部資料集，尚未經官方核對 | No |
| external_semantic_recall | TLR 或外部語意召回層 | No |
| synthetic | demo / test fixture | No，僅 demo |
| unknown | 無法確認來源或來源欄位不足 | No |

## Data-flow contract, not deployment parameters

公開版 repo 會展示使用者導入資料時建議保留的資料流介面，例如：

```text
source_manifest
-> adapter_result
-> retrieval_candidate
-> citation_verification
-> final_citations
-> trust_gate
-> answer_validation
```

但公開版不固定下列 deployment-specific tuning details：

- chunk size
- overlap
- embedding model
- vector dimension
- HNSW or vector index parameters
- SQLite FTS settings
- tuned production ranking weights
- private evaluation holdouts
- production cache layout

這不是缺漏，而是為了保留使用者依資料類型、硬體效能、更新頻率、精度需求、儲存成本與合規政策自行調整的彈性。repo 內含 demo ranking formula 與通用預設（例如 RRF、source-tier 分數），僅供展示資料流與測試契約，不代表任何 production ranking 配置。完整資料流說明請見 `docs/ARCHITECTURE_CONTRACT.md`；v0.4 的公開硬化摘要請見 `docs/V0_4_HARDENING_SUMMARY.md`。

## Promotion rule

任何 staging row 要進 production，必須滿足：

- official source 可查
- official id 可對應
- official text 可比對
- official hash 一致
- metadata 差異可解釋
- promotion manifest 記錄
- rollback 可用

## Rejection rule

以下資料不得進 current production index：

- abandon_note 非空
- category = 廢止法規
- official_hash mismatch
- official_url 無法核對
- official_not_found
- TLR-only source
- HF-only source
- source tier unknown
- candidate-only source 被要求作 final citation

## Repository rule

本 repo 不散布 production legal datasets。所有 demo 使用 synthetic data。

不得 commit 下列內容：

- government open-data downloads
- judgment SQLite shards
- law Chroma databases
- vector indexes
- official full-text caches
- TLR response caches
- HF verified full datasets
- real user query logs
- complete proprietary thesauri
- private gold evaluation holdouts
- credentials, tokens, private endpoints, or local sensitive paths

## User configuration rule

正式導入時，使用者可以自行選擇本地索引、外部語意召回、混合檢索或企業內部資料接入方式；但無論檢索層如何配置，都應保留本 repo 的核心邊界：

- retrieval candidate 不是 final citation
- external semantic recall 只能作 candidate recall
- official 或 verified_cache 才能成為 final citation 候選
- 沒有 final citation 時，trust gate 應 fail closed
- 已刪除、撤回、異動或不可公開資料應有降級、移除或停止散布機制
