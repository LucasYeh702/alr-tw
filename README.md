# ALR-TW：台灣法律 Agentic RAG / MCP Harness

[繁體中文](README.zh-TW.md) | [English](README.en.md)

ALR-TW v0.6.0 是一個 public-preview（公開預覽）的台灣法律研究安全 harness。它讓外部 agent／LLM 透過 MCP 建立研究 run，但把資料來源、研究步驟、證據升格、答案驗證與清除權限留在 server 端。設計採台灣大陸法系視角：法規時點優先，普通裁判依審級與案件角色處理，憲法法庭多數意見與個別意見分離。

本專案已整合並在 `hybrid_verified` 模式使用 [TLR（Taiwan Legal RAG）](https://github.com/aa0101181514/tw-legal-rag)進行普通裁判候選召回，再由 ALR-TW 回到司法院官方來源驗證。TLR 不會被直接當成正式引用來源。

本專案不是法律意見服務，也不是完整法律資料庫。它提供可安裝的工程框架、官方 provider、TLR 候選召回、SQLite 短期研究狀態、MCP tools、deterministic trust gates 與 synthetic tests。

本 repo 不包含 LLM，也不包含 agent 實作。規劃、工具選擇與自然語言推理由外部呼叫端提供；ALR-TW 只負責可稽核工具與確定性閘門。Repo 內的示範 ranking 參數僅供測試，不是 production ranking 設定。

> v0.6.0 仍是 `0.x` 公開預覽。介面可能調整；答案必須由具資格的人員依官方原文、時點與個案事實複核。

## 核心安全邊界

```text
外部 agent 提問／起草
  -> ALR-TW server-owned research obligations
  -> official providers + optional TLR candidate recall
  -> server-owned source/evidence snapshot
  -> claim, role, time, privacy and citation validation
  -> validated | qualified | blocked
```

- 呼叫端不能用 `source_tier=official` 自我證明來源。
- TLR 永遠只產生 `external_semantic_recall` 候選，不能直接作正式引用。
- 正式證據必須由 ALR-TW 自官方來源取得並固定內容，或由受治理 resolver 驗證 hash。
- 當事人主張、案件事實、協同意見、不同意見不得冒充法院多數理由。
- 歷史法規時點無法完整確認、證據過期、角色錯置或支持不足時 fail closed。
- `blocked` 結果不回傳 answer body。

## 資料模式

| 模式 | 外部網路 | 用途 |
|---|---|---|
| `synthetic` | 無 | 預設；離線 demo、CI、契約測試 |
| `official_only` | 僅官方來源 | 法規、憲法裁判、司法院裁判關鍵字搜尋與精確全文回查 |
| `hybrid_verified` | 官方來源 + TLR | privacy gate 通過後，以 TLR 提高普通裁判候選召回，再回官方驗證 |

啟用 `hybrid_verified` 時，通過隱私檢查的查詢文字會傳送至 TLR。不要輸入個人秘密、未公開案件事實、私有契約、訴訟策略、證據弱點或談判底線。詳見 [TLR Provider](docs/TLR_PROVIDER.md) 與 [Data Policy](DATA_POLICY.md)。

## 官方來源

- 法規：法務部全國法規資料庫的官方結構化資料與網頁一致性檢查；
- 普通裁判：直接解析司法院裁判書搜尋頁，取得 JID 後由官方 `data.aspx` 下載並解析全文；
- 憲法：憲法法庭判決、實體裁定與舊制解釋，分離主文、理由及個別意見。

第一版不承諾指定歷史日期的完整法規版本、普通裁判全域召回率、所有程序裁定正文、完整審級關係、附件／OCR 全覆蓋。詳見 [Official Providers](docs/OFFICIAL_PROVIDERS.md)。

## 安裝

需要 Python 3.11 以上。

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[all]'
```

離線預設檢查：

```bash
alr-tw doctor
alr-tw-mcp
```

Live mode（真實來源模式）必須明確選擇：

```bash
export ALR_TW_DATA_MODE=official_only
export ALR_TW_RETENTION=24h
alr-tw doctor --live
```

普通裁判不需要司法院 API token。啟用 live mode 後，關鍵字、案號及篩選條件會直接送到 `judgment.judicial.gov.tw`；不要把未公開個案事實或保密資料當成搜尋詞。

秘密不會顯示在 `doctor` 輸出，也不應寫入 `.env.example`、trace 或 SQLite。

## v0.6 MCP tools

| Tool | 用途 |
|---|---|
| `research_legal_question` | 建立 server-owned research run，不生成答案 |
| `continue_legal_research` | 以 `operation_id` 執行一個下一步 obligation |
| `get_legal_research_state` | 唯讀取得狀態，不做網路請求、不延長 TTL |
| `lookup_legal_source` | 精確查詢法規條文、憲法字號、JID 或正式裁判字號 |
| `validate_legal_answer` | 只用該 run 的 server-owned evidence 驗證草稿 |
| `purge_research_storage` | 同步刪除單一 run 或全部 managed storage |

舊版 synthetic／trace tools 暫時保留相容性，但新整合應優先使用上述研究服務。MCP tool output 仍使用：

```json
{
  "ok": true,
  "schema_version": "alr-tw.mcp_tool_result/v1",
  "data": {},
  "error": null
}
```

支援的 MCP protocol versions：`2025-11-25`、`2025-06-18`、`2025-03-26`、`2024-11-05`。不支援的版本會在 initialize 階段拒絕。

## 研究流程

標準 run 依序處理 query understanding、privacy screen（只限 hybrid）、law research、judgment recall、official verification、counter-authority limitation、time context、evidence sufficiency 與 final validation。每次 `continue_legal_research` 只執行一個 obligation，方便 agent 觀察、重試與稽核。

Final decision：

- `validated`：來源、時點、角色與 claim support 通過；
- `qualified`：已驗證來源足以支持草稿，但普通裁判召回等覆蓋有明示限制；
- `blocked`：不可展示草稿，回傳 blockers 而不回 answer body。

`lookup_legal_source` 只證明來源查得，不代表任何答案 claim 已被驗證。

## Retention 與清除

預設短期 SQLite 儲存位置為 `~/.cache/alr-tw`，預設保留 `24h`，上限 `7d`。單次 run 可用 `retention: "ephemeral"`，在 final validation 後同步清除。

```bash
alr-tw purge --run RUN_ID --confirm
alr-tw purge --all --confirm
```

CLI 與 MCP 共用同一 purge 實作。清除本機資料無法撤回已傳送給外部服務的查詢或其日誌。詳見 [Storage and Purge](docs/STORAGE_AND_PURGE.md)。

## 開發驗證

```bash
uv run ruff check .
uv run mypy src
uv run pytest -q
python3 scripts/check_no_forbidden_files.py
python3 scripts/check_public_boundary.py
uv build
```

## 公開／私有邊界

Repo 不含 production corpus、官方全文永久快取、真實使用者紀錄、私有 eval、向量 shard、憑證或內部 endpoint。Synthetic data 只能用於 demo／測試，不能被描述為現行法。正式部署者必須自行確認官方資料授權、個資、保存、移除與服務條款。

## 文件

- [Architecture](ARCHITECTURE.md)
- [Architecture Contract](docs/ARCHITECTURE_CONTRACT.md)
- [Trust Model](docs/TRUST_MODEL.md)
- [Tool Contract](docs/TOOL_CONTRACT.md)
- [TLR Provider](docs/TLR_PROVIDER.md)
- [Official Providers](docs/OFFICIAL_PROVIDERS.md)
- [Storage and Purge](docs/STORAGE_AND_PURGE.md)
- [v0.6.0 Release Audit](docs/V060_RELEASE_AUDIT.md)
- [Security](SECURITY.md)
- [Changelog](CHANGELOG.md)

## 法律聲明

本專案僅供軟體架構、研究與測試，不構成法律意見、律師服務或任何個案結論，也不保證資料完整、正確、即時或適用。
