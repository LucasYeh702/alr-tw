# ALR-TW 下一階段修正規格書

本規格書彙整 GPT-5.5 Pro、Claude Fable 5、AGY 以及本地 Codex 驗證後的審查結果，作為下一輪公開版 hardening patch 的工程規格。

## 審查結論

目前公開宣稱可以成立，但必須保留明確限定：

> ALR-TW 是由 AI agent 驅動、bounded、deterministic、public-safe 的 Agentic Legal RAG / MCP Harness for Taiwan Law。

本 repo 應持續避免以下宣稱：

- production legal agent
- autonomous legal agent
- real Taiwan legal database
- full claim-level grounding engine
- production legal research platform

下一輪工作目標不是擴大宣稱，而是補強目前已接受宣稱背後的工程證據。

## 範圍

目標版本：`v0.2.1` hardening patch。

主要目標：讓公開 repo 更清楚、也更機械化地支撐「agentic RAG harness」這個名稱，同時避免被誤解成 production autonomous legal agent。

允許納入公開 repo 的內容：

- synthetic demo data
- framework code
- deterministic traces
- tests
- CI
- docs
- public-safe validation examples

不在本次範圍內：

- production corpus
- 真實法律全文
- 私有 cache 或 vector index
- 私有 ranking / chunking 參數
- production claim-grounding runtime
- external provider credentials
- user records 或 logs

## 外審意見統整

| 發現 | 來源 | 判定 | 修正項目 |
|---|---|---|---|
| 目前宣稱可成立，但只能作為 bounded、deterministic、public-safe reference harness | GPT-5.5 Pro、Claude、AGY | 採納 | 保留現有定位與 caveats |
| PII masking 能力被說得太滿 | Claude、本地驗證 | 採納 | F1 |
| demo `tool_calls` 容易被誤解成真實執行過的 tools | Claude、本地驗證 | 採納 | F2 |
| `human_review_required` 仍可能帶有 answer | Claude、本地驗證 | 採納 | F3 |
| trust gate 在有 final citation 時可能把 critical failure 降級成 human review | AGY、本地 probe | 採納為設計風險 | F3 |
| MCP `validate_citation` 無法表達完整 `verified_cache` metadata | Claude、本地驗證 | 採納 | F4 |
| `support: supported` 會過度暗示已做 claim support | Claude、本地驗證 | 採納 | F4 |
| legacy `agentic_legal_research` schema 與 `alr-tw.agentic_trace/v1` 漂移 | Claude、AGY | 採納 | F5 |
| error code 與 failure reason enum 應統一 | GPT-5.5 Pro | 採納 | F6 |
| Trace JSON 規格仍需補完整 | GPT-5.5 Pro | 採納 | F2、F7 |
| TLR candidate mode 需要明確文件 | GPT-5.5 Pro | 採納 | F8 |
| MCP protocol negotiation 與 stdio hygiene 可再 harden | AGY | 採納，較低優先 | F9 |
| lookup tools 缺少 MCP-level positive tests | AGY | 採納 | F10 |
| Legal Effect Schema、private claim grounding、enterprise adapters | GPT-5.5 Pro | 僅列 roadmap | R1-R3 |

## F1. Privacy Masking 邊界

### 問題

README 目前寫 query understanding 會遮罩敏感資訊。實際上目前 demo masking 是 heuristic，且對常見未分詞中文輸入會失效，例如中文姓名旁邊接其他字、或台灣身分證字號緊接中文文字。

### 需求

- 將公開能力從廣義的「sensitive information masking」改成「demo heuristic masking」。
- 文件明確寫出這不是 production PII redaction。
- 新增測試，覆蓋未分詞中文姓名與相鄰台灣身分證字號。
- 可二擇一：
  - 改善 regex 實作，讓上述案例通過。
  - 若暫不改善實作，必須把失敗案例寫成明確 known limitation。

### 驗收條件

- README 與 `docs/AGENTIC_HARNESS_ACCEPTANCE.md` 不再暗示 production-grade PII redaction。
- 測試覆蓋：
  - `王小明想問押金`
  - `身分證王小明A123456789`
  - 既有的空白分隔 demo input
- public boundary checker 通過。

## F2. Trace 語意與 Tool Call 證據

### 問題

`run_agentic_demo` 目前會對每個 graph step 產生一筆 successful `ToolCallTrace`。但這些是 deterministic harness trace，不是真正由多個外部 tool live 執行後留下的 runtime log。

### 需求

- 文件與 trace schema 必須明確說明：
  - `run_agentic_demo` trace 是 deterministic harness trace。
  - `tool_calls` 是 harness-recorded step records；只有接上真實 tool adapter 時才代表實際 tool execution。
- 在 trace 中加入欄位或 summary marker，區分 synthetic harness step 與 actual executed tool。
- 擴充 `docs/TRACE_SCHEMA.md`，補上 top-level fields、nested fields、allowed values。
- 增加 decision trace，記錄 final action 為何被選出。

### 驗收條件

- example traces 明確可看出 synthetic / demo 性質。
- tests 會檢查 trace schema 欄位與 allowed values。
- README 不再讓讀者以為 synthetic `tool_calls` 是 live external tool execution logs。

## F3. Trust Gate Final Action Contract

### 問題

目前 trust gate 允許 `human_review_required` trace 仍帶有 `answer`。此外，只要 final citation 存在，內部 gate 在某些 critical failure 同時存在時仍可能回傳 `human_review_required`。

### 需求

- 定義 critical failure reasons；這些原因一律產生 `refuse`。
- 只有在以下條件同時成立時，才允許 `human_review_required`：
  - final citation exists
  - no rejected or unverifiable citation exists
  - required coverage is not low
  - 唯一未解 blocker 是 claim-support 或 human review
- 當 `final_action != "answer"` 時，`answer = None`。
- 文件明確規定 client display rule：
  - client 只能在 `safe_to_present == true` 且 `final_action == "answer"` 時渲染 answer content。

### 驗收條件

- unit tests 覆蓋：
  - official citation + claim-support unchecked => `human_review_required`
  - official citation + rejected source => `refuse`
  - low coverage + human review flag => `refuse`
  - `human_review_required` trace 不帶 answer body
- 既有 pass / refuse scenarios 保持穩定。

## F4. Citation Eligibility 與 Verified Cache Contract

### 問題

MCP `validate_citation` tool 目前只接受 `citation_id` 與 `source_tier`。因此 docs 說的 `verified_cache` positive path 在 MCP 層無法觸發。另外，`support: supported` 容易被理解成已做 claim support 或 entailment，但目前邏輯只是在判斷 source-tier eligibility。

### 需求

- 替換或澄清 `support` 語意：
  - 改成 `eligibility` 或 `citation_eligibility`。
  - 或除非真的做 claim support，否則 `support` 一律回 `not_checked`。
- MCP optional arguments 新增：
  - `official_url`
  - `official_hash`
  - `verified_at`
  - `source_label`
- 補 complete / incomplete `verified_cache` 的 MCP tests。
- 更新 `docs/TRUST_MODEL.md` 與 `docs/TOOL_CONTRACT.md`。

### 驗收條件

- metadata 完整的 `verified_cache` 可透過 MCP 回傳 final-eligible。
- metadata 不完整的 `verified_cache` 仍 fail closed。
- 任何 public API 不得暗示已做完整 claim-level entailment，除非實際真的做了該檢查。

## F5. Schema 統一

### 問題

公開 trace schema 是 `alr-tw.agentic_trace/v1`，但 legacy `agentic_legal_research` 回傳 `alr-tw.agentic-legal-rag/v1`，shape 也不同。

### 需求

- 二擇一：
  - 將 `agentic_legal_research` 遷移成 canonical trace schema。
  - 或明確標示為 legacy tool，並完整文件化 schema 差異。
- 除非會破壞 compatibility tests，否則優先採 canonical migration。
- 集中管理 schema constants。

### 驗收條件

- `docs/TRACE_SCHEMA.md` 列出所有仍會公開輸出的 schema names。
- tests 檢查所有 MCP tools 都回傳已文件化的 schema version。
- 不存在未文件化的 public schema。

## F6. Error Code 與 Failure Reason Enum

### 問題

failure reasons 與 error codes 目前散落在 trust gate、citation validation、docs、examples 中，多處使用 string literals。

### 需求

- 建立 shared enums 或 constants：
  - trust failure reasons
  - citation validation error codes
  - final actions
  - citation uses
- docs / examples 必須由 constants 產生，或至少由測試驗證與 constants 一致。
- 對齊 `docs/ERROR_CODES.md`、`docs/TRUST_MODEL.md` 與 tests。

### 驗收條件

- core logic 不再重複散落未型別化的 failure-reason literals。
- 若 docs / examples 出現未知 failure reason，tests 必須失敗。

## F7. 完整 Trace JSON 規格

### 問題

GPT-5.5 Pro 指出目前 trace spec 對一個 public harness 來說仍過短。

### 需求

- 擴充 `docs/TRACE_SCHEMA.md`，至少包含：
  - top-level object fields
  - field types
  - allowed enum values
  - nullability
  - final-action semantics
  - synthetic vs actual tool call semantics
  - decision trace shape
- 從 trace spec 連到 example trace files。

### 驗收條件

- trace examples 符合文件化 shape。
- `test_trace_schema.py` 覆蓋 required fields 與 enum values。

## F8. TLR Candidate Mode 文件

### 問題

目前已描述 external semantic recall，但 candidate-only operating mode 還需要更清楚的公開文件。

### 需求

- 新增一節或一份文件，說明 TLR / external semantic candidate mode。
- 明確寫出 external recall 可以提高 candidate discovery，但不能在未經 official 或 verified-cache validation 前成為 final citation。
- 加入 scenario diagram 或 table，至少覆蓋：
  - external candidate discovered
  - candidate classified as candidate-only
  - official verification missing
  - final action refuses or asks for review

### 驗收條件

- README 連到 candidate-mode 文件。
- candidate-only examples 與 reports 被交叉連結。

## F9. MCP Stdio 與 Protocol Robustness

### 問題

AGY 提出幾個較低優先但合理的 MCP robustness issues：

- strict protocol version rejection
- possible stdout contamination
- tool errors returned as JSON-RPC protocol errors

### 需求

- 先決定本專案目標是 strict minimal JSON-RPC demo behavior，還是 broader MCP client compatibility。
- 若選擇 broader compatibility：
  - unsupported protocol version 應 negotiation 回 server version
  - `main` 中將意外 stdout logging 導到 stderr，避免污染 stdio JSON-RPC channel
  - tool execution failures 應在適當情況下回 MCP tool errors

### 驗收條件

- tests 覆蓋 unsupported protocol version behavior。
- tests 覆蓋 tool-level error response policy。
- stdio smoke 仍通過。

## F10. MCP Tool Coverage

### 問題

lookup tools 與 trust-model tools 的 MCP-level test coverage 低於 agentic demo path。

### 需求

- 新增 MCP JSON-RPC tests：
  - `get_trust_model`
  - `validate_citation` official
  - `validate_citation` complete verified cache
  - `validate_citation` incomplete verified cache
  - `exact_law_lookup`
  - `exact_judgment_lookup`
  - `exact_constitutional_lookup`
  - unknown `run_agentic_demo` scenario

### 驗收條件

- 所有 public MCP tools 至少有一個 success-path test。
- trust / validation failures 至少有一個 fail-closed test。

## Roadmap Items

以下項目不列入 `v0.2.1` 必修範圍。

### R1. Legal Effect Schema

定義 synthetic、public-safe 的 legal effect classification schema，例如 procedural effect、remedy type、temporal applicability、citation authority。

### R2. Private Runtime Claim-Level Grounding

Claim-level grounding 應先留在 private runtime。除非能用 synthetic fixtures 表達，否則不放入 public reference implementation。公開 repo 只應把它文件化為 extension point。

### R3. Enterprise Workflow Adapter

未來可提供 enterprise review workflow integration layer。但在 public repo 中必須維持 adapter-only，不得包含 private workflow data。

## 建議實作順序

1. F3 Trust Gate Final Action Contract
2. F4 Citation Eligibility And Verified Cache Contract
3. F5 Schema Unification
4. F2 Trace Semantics And Tool Call Evidence
5. F6 Error Code And Failure Reason Enum
6. F1 Privacy Masking Boundary
7. F7 Complete Trace JSON Specification
8. F8 TLR Candidate Mode Documentation
9. F10 MCP Tool Coverage
10. F9 MCP Stdio And Protocol Robustness

前六項應在下一個 release tag 前完成。

## 必跑驗證

任何 follow-up push 前必須通過：

```bash
git diff --check
python3 scripts/check_no_forbidden_files.py
python3 scripts/check_public_boundary.py
uv run --extra dev ruff check .
uv run --extra dev pytest
uv run --extra dev alr-tw-demo
uv run --extra dev python examples/agentic_mcp_client_demo.py
```

若有 MCP changes，另需跑 stdio smoke，覆蓋 initialize、initialized notification、tools/list、tools/call。

## Definition Of Done

本 hardening patch 完成時，必須滿足：

- docs 與 code 對「宣稱什麼 / 不宣稱什麼」一致
- 所有 public schema versions 都已文件化並有測試
- human-review outputs 不會被誤渲染成 safe answers
- verified-cache positive / negative paths 可透過 MCP 測試
- trace examples 明確標示 synthetic harness traces
- public safety checks 與 full tests 通過
- `ASK_YOUR_AI_AGENT_FULL_RAG.zh-TW.md` 除非另行明確核准，否則維持 untracked 且 excluded
