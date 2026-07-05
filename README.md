# ALR-TW：台灣法律 Agentic RAG / MCP Harness

語言版本：繁體中文 | [English](README.en.md)

ALR-TW 是 **Agentic Legal RAG / MCP Harness for Taiwan Law** 的簡稱。它是一個約束外部 AI agent 的 agentic RAG harness：外部 agent 可以呼叫工具並取得 trace，但必須在 harness 的 deterministic graph、citation validation 與 trust gate 內運作。它不是自主執業、可自行完成法律判斷的 autonomous legal agent。

本 repo 不包含 LLM，也不包含 agent 實作。規劃、選工具與自然語言推理的 agent 角色由呼叫端（外部 MCP client 或 LLM runtime）提供；ALR-TW 提供工具介面、確定性閘門圖與 trace / 報告契約，用來約束該外部 agent。Trust-gate decision 由 deterministic harness 做出，不由 agent 自行宣告。

本 repo 是 public-safe 的參考實作，用來示範法律 AI agent 在回答前如何規劃檢索、召回候選資料、判斷來源層級、驗證引用、檢查覆蓋率，最後在證據不足時 fail closed。

這個 repo 的重點不是「內建台灣法律資料庫」，而是「讓法律 RAG agent 不跳過查證流程」。它提供 deterministic execution graph、MCP tools、trust gate、trace schema、validation report 與 synthetic scenarios，讓開發者可以用公開安全的方式檢查 agentic legal RAG 的工程邊界。

> [!IMPORTANT]
> 本專案只包含 synthetic demo data、framework code、tests、CI 與 docs。本專案不提供真實法律全文、production corpus、官方全文快取、向量資料庫、使用者紀錄、私有 eval set 或法律意見。

## Agentic RAG 能力

ALR-TW 把法律 RAG 拆成可審計的 agent loop：

```text
User Query
-> Query Understanding
-> Source Plan
-> Retrieval
-> Source Classification
-> Citation Validation
-> Coverage Gate
-> Trust Gate
-> Final Decision
```

這個 loop 是用來約束外部 agent 的 bounded agentic workflow，不是無限制自治代理。外部 agent 可以使用工具並讀取 trace；final action 與 trust-gate decision 仍由 deterministic harness 根據 citation validation、coverage 與 claim support 狀態產生。

ALR-TW 目前示範的能力：

- query understanding：用 demo heuristic 遮罩敏感資訊、正規化查詢、解析法律引用與 issue tags
- source planning：把官方來源、verified cache、staging、external semantic recall、synthetic fixture 分層
- candidate retrieval：召回 synthetic 法規、裁判、憲法法庭資料與外部候選線索
- exact lookup：用法律名稱與條號、裁判 `jid`、憲法法庭 synthetic id 做精確查找
- citation validation：判斷 citation 是否存在、是否可驗證、是否可作 final citation
- coverage gate：回報 laws、judgments、constitutional materials 等覆蓋狀態
- trust gate：沒有 final citation、來源不可驗證、coverage 低信心或 claim support 未檢查時拒絕輸出
- claim grounding：v0.3 新增 answer claim 切分與語意對齊檢核，讓主張與證據可追溯
- identifier-backed verified cache：v0.4 新增 opt-in 的 JID / official identifier 驗證路徑，但必須由 resolver 回到本地官方原始檔並重算 hash 才能通過
- trace schema：輸出 `alr-tw.agentic_trace/v1`，保留 steps、tool calls、decision trace、evidence、coverage、trust gate 與 final action
- validation report：把 agent run 轉成可 review 的 Markdown report
- MCP server：用 stdio 暴露 agentic legal RAG tools，讓本機 MCP client 啟動

## MCP Tools

| Tool | 能力 | 輸出重點 |
|---|---|---|
| `agentic_legal_research` | 執行 synthetic agentic RAG loop | canonical trace、candidate、final citation、trust gate |
| `run_agentic_demo` | 執行 deterministic ALR-TW scenario | `answer`、`refuse` 或 `human_review_required` |
| `build_validation_report` | 產生 validation report | Markdown review artifact |
| `get_trust_model` | 回傳 source tier 與 fail-closed policy | trust model |
| `get_claim_grounding_policy` | 取得 v0.3 claim grounding 合約與支援狀態定義 | claim policy |
| `extract_answer_claims` | 將 answer 拆成可追溯的 claim 單位 | answer claims |
| `check_claim_support` | 用 evidence segments 檢查 claim，輸出 claim_support 與 semantic failure summary | claim support status |
| `legal_search` | synthetic legal search demo | candidate retrieval |
| `validate_citation` | 驗證 citation tier、metadata 與 opt-in identifier-backed cache 使用資格 | final eligibility |
| `exact_law_lookup` | synthetic 法規精確查找 | demo-only result |
| `exact_judgment_lookup` | synthetic 裁判精確查找 | demo-only result |
| `exact_constitutional_lookup` | synthetic 憲法法庭資料精確查找 | demo-only result |

所有 MCP tool result 都包在同一個 envelope：

```json
{
  "ok": true,
  "schema_version": "alr-tw.mcp_tool_result/v1",
  "data": {},
  "error": null
}
```

範例 trace 中的 `tool_calls` 會標示 `execution_mode: "harness_recorded"`，代表這是 deterministic harness record，不是 live external tool execution log。

## Claim Grounding（v0.3）

v0.3 在不改變來源安全門檻的前提下，新增語意層防線：

- `extract_answer_claims`：把答案切成可追蹤的 claim 單位（`alr-tw.answer-claim/v1`）
- `check_claim_support`：檢查每個 claim 是否有對應 evidence span 支持（`alr-tw.claim-support/v1`）
- `get_claim_grounding_policy`：回傳 claim 狀態定義、風險旗標與合約邊界（`alr-tw.claim-grounding-policy/v1`）

此版本仍是 public-safe 的示範：僅公開 schema、synthetic fixture、MCP contract 與測試，不公開完整的 production 語意推理引擎。

## Identifier-Backed Verified Cache（v0.4）

v0.4 新增 opt-in 的 `verified_cache` 路徑：對 judgment record，穩定官方識別碼（例如 JID）可以在特定條件下替代官方 URL。這不是放寬引用門檻；它把門檻改成 resolver-backed verification：

- 預設關閉，必須設定 `ALR_TW_IDENTIFIER_BACKED_VERIFIED_CACHE=1` 才啟用。
- 僅限 `legal_material_type: "judgment"`；法規與憲法資料仍要求官方 URL。
- resolver 必須將 identifier 對回本地下載的官方原始檔。
- 系統必須重新計算原始紀錄的 content hash，且與 citation 宣告的 `official_hash` 相符。
- unresolved identifier、hash mismatch、未啟用 opt-in、非 judgment material 都會 fail closed。

公開 repo 只提供 synthetic demo resolver，用來測試 allow / reject 路徑；正式部署需要 operator 自行接上合法取得的司法院原始資料快取。

## Trust Gate

ALR-TW 的核心規則是：retrieval candidate 不等於 final citation。

| Source tier | 角色 | 可作 final citation |
|---|---|---|
| `official` | 官方或官方根據來源 | Yes |
| `verified_cache` | 有官方 URL，或 opt-in identifier resolver + content hash + verified time 的快取 | Conditional |
| `staging` | 匯入或 audit 候選資料 | No |
| `external_semantic_recall` | 外部語意召回候選 | No |
| `synthetic` | demo / test fixture | No |
| `unknown` | 未知來源 | No |

Trust gate 會在下列情況 fail closed：

- 沒有 final citation
- citation 被拒絕或不可驗證
- 只找到 candidate-only source
- 只找到 synthetic demo source
- verified cache 缺少官方 URL、hash 或驗證時間
- identifier-backed verified cache 未啟用、未解析、hash mismatch，或不是 judgment record
- coverage 為 absent 或 low confidence
- claim support 狀態非安全展示形態（如 `partially_supported`、`overstated`、`unsupported`、`contradicted`、`role_error`、`unchecked`、`needs_review`）
- claim support 尚未檢查時只能進入 human review，不會輸出可直接呈現的 answer body

## Demo Scenarios

`examples/agentic_runs/*.json` 保留 deterministic traces；`examples/reports/*.md` 保留對應 validation reports。

| Scenario | 預期結果 |
|---|---|
| `pass_official_source` | 有 final citation，且 claim 被支持，允許回答 |
| `pass_claim_supported` | 有 final citation 且 claim support 狀態為 supported，允許回答 |
| `fail_candidate_only` | 外部召回只能當候選，拒絕回答 |
| `fail_synthetic_only` | synthetic fixture 不能當現行法律，拒絕回答 |
| `fail_verified_cache_incomplete` | verified cache metadata 不完整，拒絕回答 |
| `fail_no_final_citation` | 沒有 final citation，拒絕回答 |
| `fail_low_coverage` | 覆蓋率低信心，拒絕回答 |
| `fail_party_argument_as_court_view` | party_argument 被誤述為法院見解，拒絕/需人工複核 |
| `fail_overstated_case_specific_rule` | 案件事實外推為普遍規則，需人工複核或拒絕 |
| `fail_unsupported_paraphrase` | 對應證據找不到支撐，拒絕回答 |
| `human_review_required_claim_support` | 來源存在，但 claim support 未檢查，需要人工審查 |
| `human_review_claim_unchecked` | 同上，但以情境名稱 `human_review_claim_unchecked` 驗證 alias 行為 |

當 `final_action != "answer"` 時，trace 的 `answer` 必須是 `null`。Client 只有在 `trust_gate.safe_to_present == true` 且 `final_action == "answer"` 時才能渲染 answer content。

## 快速開始

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .[dev]

uv run --extra dev alr-tw-demo
uv run --extra dev python examples/agentic_mcp_client_demo.py
```

MCP stdio smoke：

```bash
printf '%s\n' \
  '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"stdio-smoke","version":"0.4.0"}}}' \
  '{"jsonrpc":"2.0","method":"notifications/initialized"}' \
  '{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}' \
  | uv run --extra dev alr-tw-mcp
```

驗證：

```bash
python3 scripts/check_no_forbidden_files.py
python3 scripts/check_public_boundary.py
uv run --extra dev ruff check .
uv run --extra dev pytest
```

## Public / Private Boundary

本 repo 是公開 reference harness，只保留可公開的工程面：

- source policy
- citation validator
- trust gate
- deterministic execution graph
- trace schema
- synthetic fixtures
- tests、CI、docs

本 repo 不包含：

- production legal datasets
- official full-text caches
- SQLite shards
- Chroma / vector DB
- real verified cache
- real user query records
- private workflow data
- production ranking、chunking、index 參數
- credentials、private endpoints、local sensitive paths

Public repo 只示範「邊界與契約」。正式系統可以把 synthetic adapters 換成符合法規、授權與隱私要求的資料來源，但仍應保留同一套 source tier、citation validation、coverage gate 與 trust gate。

## 如何接入真實資料

ALR-TW 刻意不公開調校後的 production ranking 參數，也不提供固定 chunk size、embedding model、vector dimension 或 HNSW 設定。repo 內仍包含 demo ranking 公式與通用預設（例如 RRF、source-tier 分數），只用來展示資料流與測試契約，不代表任何閉源 runtime 的實際配置；實作者應依資料規模、硬體、更新頻率、授權條件與 precision / latency 需求自行量測決定。

建議接入順序：

```text
Official data source or compliant internal source
-> Source adapter
-> Staging index
-> Official verification
-> Source trust policy
-> Citation validation
-> Retriever / MCP tools
-> Trust gate
```

外部語意召回可以提高 recall，但在 ALR-TW 中永遠先視為 `external_semantic_recall`，只能當 candidate。Final citation 必須回到 `official` 或符合條件的 `verified_cache`。

實務上可以把 TLR 或其他語意索引作為高召回資料源，用來找候選裁判與相關線索。但 final citation 不應直接引用 TLR 召回結果；建議仍自司法院或其他官方來源下載原始檔，建立本地 `verified_cache`。

本地 `verified_cache` 至少應保留官方 URL 或穩定官方識別碼、content hash、下載時間與 verified time。只有 `official` 或 metadata 完整的 `verified_cache` 才能通過 final-citation eligibility。

最小資料建議：

- search / semantic recall：先接 TLR 或其他語意索引，作為高召回 candidate source。
- official access prerequisite：本專案不提供司法院 API credential、不代為申請，也不重散布司法院資料；使用者須自行取得必要官方 access，或以合法方式下載官方原始檔。
- local verification cache：使用者自行下載司法院裁判原始月檔後，轉成本地 `verified_cache`，用來核對 jid、官方來源、hash 與 verified time。
- why local data is still needed：即使已接上 TLR，TLR 仍只是 candidate recall；final citation eligibility、content hash、可重現資料快照與敏感後續驗證仍必須回到本地官方資料快取。
- law corpus：法規資料不屬於司法院裁判月檔，應另接法務部或其他官方法規來源。以官方法規 JSON 的實測量級估算，原始法規資料約數百 MB 以內；若另建法規 vector index，通常是 1-2GB 級別。明確條號查詢應優先走 exact article lookup，再補語意召回。
- constitutional materials：司法院公開資料也可另外接釋字與憲法法庭資料，作為 constitutional materials 的本地驗證來源。以實測量級估算，raw zip 約 260MB、raw JSON 約 25MB，若保留附件與 OCR text，整體約 1GB 以內。
- Judicial Yuan scope：這裡的司法院資料主要指司法院開放資料的裁判書月檔，以及可另行接入的釋字與憲法法庭公開資料。它不包含法規全文、行政函釋、法務部法規資料、未公開裁判或任何私有案件資料；實際可下載期間、欄位與遮蔽內容以司法院開放資料站為準。
- capacity planning：以完整歷史裁判資料量級估算，官方壓縮月檔約 50GB，轉成本地 gzip 驗證快取約 30GB；若另外自建裁判全文、FTS 或 vector index，容量可能上升到數百 GB。最小部署可先預留約 100GB 給官方裁判原始檔與本地驗證快取；法規原始檔與憲法資料各預留 1GB 以內通常足夠，index 層視需求另外規劃。

## 規格文件

- [docs/AGENTIC_WORKFLOW.md](docs/AGENTIC_WORKFLOW.md)：agentic RAG execution graph
- [docs/AGENTIC_HARNESS_ACCEPTANCE.md](docs/AGENTIC_HARNESS_ACCEPTANCE.md)：v0.4.0 名稱與 release acceptance 條件
- [docs/TRUST_MODEL.md](docs/TRUST_MODEL.md)：source tier、citation use 與 fail-closed rules
- [docs/TLR_CANDIDATE_MODE.zh-TW.md](docs/TLR_CANDIDATE_MODE.zh-TW.md)：外部語意召回 / TLR-like candidate-only 模式（[English](docs/TLR_CANDIDATE_MODE.md)）
- [docs/TOOL_CONTRACT.md](docs/TOOL_CONTRACT.md)：MCP tool envelope 與工具契約
- [docs/TRACE_SCHEMA.md](docs/TRACE_SCHEMA.md)：trace schema
- [docs/VALIDATION_REPORT.md](docs/VALIDATION_REPORT.md)：validation report 結構
- [docs/RELEASE_NOTES.md](docs/RELEASE_NOTES.md)：release notes
- [docs/V0_4_HARDENING_SUMMARY.md](docs/V0_4_HARDENING_SUMMARY.md)：v0.4 public hardening summary
- [docs/RELEASE_AUDIT_PROCEDURE.md](docs/RELEASE_AUDIT_PROCEDURE.md)：公開 release audit 規程
- [docs/DEPLOYMENT_STARTING_POINTS.md](docs/DEPLOYMENT_STARTING_POINTS.md)：illustrative deployment starting points
- [docs/PUBLIC_PRIVATE_BOUNDARY.md](docs/PUBLIC_PRIVATE_BOUNDARY.md)：公開 repo 與 private runtime 邊界
- [docs/PUBLIC_PRIVATE_TRACEABILITY.md](docs/PUBLIC_PRIVATE_TRACEABILITY.md)：local capability 與 public counterpart 對應
- [docs/ERROR_CODES.md](docs/ERROR_CODES.md)：錯誤碼
- [docs/THREAT_MODEL.md](docs/THREAT_MODEL.md)：公開 reference repo 威脅模型
- [docs/ARCHITECTURE_CONTRACT.md](docs/ARCHITECTURE_CONTRACT.md)：替換 adapter / retriever 時必須保留的架構契約

## 法律聲明

本專案只用於法律 AI 架構展示與工程測試，不提供法律意見，不構成法律服務，也不保證任何法律資訊的完整性、正確性、即時性或適用性。

實際法律分析或引用應回到官方來源核對，並由合格法律專業人士審查。

## English Summary

ALR-TW is an Agentic Legal RAG / MCP Harness for Taiwan Law. It demonstrates a bounded agentic legal RAG loop with source planning, retrieval, citation validation, coverage gates, trust gates, claim-grounding checks, opt-in identifier-backed verified-cache checks, trace schema, validation reports, and MCP tools using synthetic demo data only.
