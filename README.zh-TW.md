# ALR-TW：台灣法律 Agentic RAG / MCP Harness

繁體中文 | [English](README.en.md)

ALR-TW v0.6.2 是台灣法律研究安全 harness 的官方網頁相容性修正版。外部 agent／LLM 可透過 MCP 建立研究 run；來源取得、研究義務、證據升格、答案驗證與清除則由 server 掌控。架構採台灣大陸法系角度：現行法規與法律時點優先，普通裁判依審級及段落角色處理，憲法法庭多數理由、協同意見與不同意見分離。

本專案已整合並在 `hybrid_verified` 模式使用 [TLR（Taiwan Legal RAG）](https://github.com/aa0101181514/tw-legal-rag)尋找普通裁判候選，再由 ALR-TW 回查司法院官方全文；TLR 結果本身不是正式引用證據。

本專案不是法律意見服務，也不是完整法律資料庫。

本 repo 不包含 LLM，也不包含 agent 實作。規劃、工具選擇與自然語言推理由外部呼叫端提供；ALR-TW 只負責可稽核工具與確定性閘門。Repo 內的示範 ranking 參數僅供測試，不是 production ranking 設定。

> v0.6.2 仍是 `0.x` 預覽版本。答案必須由具資格的人員依官方原文、時點與個案事實複核。

## Agentic RAG 能力

ALR-TW 把法律研究拆成可觀察、可重試且可稽核的 server-owned 流程：

```text
User query
  -> query understanding and privacy screen
  -> law / judgment / constitutional source plan
  -> retrieval and candidate classification
  -> official-source resolution and evidence promotion
  -> time, role, coverage and claim-support checks
  -> citation validation
  -> validated | qualified | blocked
```

v0.6.2 提供 query understanding、outbound/output privacy 分離、法規／裁判／憲法來源規劃、TLR 候選官方升格、partial source 保留、裁判角色分類、explicit claim bindings、deterministic grounding v2、短期 resumable run 與 deterministic finalization。另補強舊式 `hlExportPDF`、`/EXPORTFILE/ExportToPdf.aspx` 裁判頁、TLR 五段 doc ID 的官方 canonical 補全、搜尋結果 fallback、今日現行法日期語意與 TLR 本地重排。公開版尚未實作系統性反方裁判搜尋。

外部 agent 可以規劃研究與起草答案，但不能自行宣告來源為官方資料、把候選升格成證據，或繞過最終驗證。

## v0.6.2 的安全模型

```text
外部 agent 提問／起草
  -> server-owned research obligations
  -> official providers + optional TLR candidate recall
  -> server-owned evidence snapshots
  -> claim / role / time / privacy / citation validation
  -> validated | qualified | blocked
```

- 呼叫端宣告 `official` 不會自動取得正式引用資格；
- TLR 只提供 `external_semantic_recall` 候選，必須回官方來源驗證；
- 當事人主張、案件事實、協同／不同意見不能冒充法院多數見解；
- 歷史時點、來源到期、角色或主張支持無法確認時 fail closed；
- `blocked` 不回傳 answer body。

## 三種資料模式

| 模式 | 行為 |
|---|---|
| `synthetic` | 預設、完全離線，供 demo 與 CI |
| `official_only` | 只連官方法規、普通裁判與憲法法庭來源 |
| `hybrid_verified` | privacy gate 通過後送 TLR 找候選，再回官方驗證 |

啟用 `hybrid_verified` 時，查詢文字可能傳送至 TLR。不得輸入個人秘密、未公開個案事實、私有契約、訴訟策略、證據弱點或談判底線。詳見 [TLR Provider](docs/TLR_PROVIDER.md)。

## 安裝與設定

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[all]'

alr-tw doctor
```

真實官方模式：

```bash
export ALR_TW_DATA_MODE=official_only
export ALR_TW_RETENTION=24h
alr-tw doctor --live
```

普通裁判不需要司法院 API token。啟用 live mode 後，搜尋詞與篩選條件會直接送到司法院裁判書查詢網站；不得以未公開案情、個人秘密或受保密義務保護的資料作為搜尋詞。也不要把 TLR API key 或真實查詢寫入 repo。

## v0.6.2 MCP tools

| Tool | 用途 |
|---|---|
| `research_legal_question` | 建立研究 run，不生成答案 |
| `continue_legal_research` | 以 idempotent `operation_id` 執行一個下一步 |
| `get_legal_research_state` | 唯讀讀取 run 狀態 |
| `lookup_legal_source` | 精確查詢法規、憲法字號、JID／正式裁判字號 |
| `validate_legal_answer` | 只用該 run 的 server-owned evidence 驗證草稿 |
| `purge_research_storage` | 清除單一 run 或全部 managed storage |

舊版 synthetic／trace tools 暫時保留相容性。新整合應使用上述 server-owned research flow。

支援 MCP protocol `2025-11-25`、`2025-06-18`、`2025-03-26`、`2024-11-05`。

所有 tool result 都使用固定 envelope：

```json
{
  "ok": true,
  "schema_version": "alr-tw.mcp_tool_result/v1",
  "data": {},
  "error": null
}
```

`request_id`／`client_id` 只用於關聯紀錄；會改變狀態的操作以 `operation_id` 保持冪等。未知欄位、不支援的 protocol version、caller 自帶的 trust decision 或不合法 purge 請求都會被拒絕。

## 官方 providers

- 法務部法規：官方結構化資料優先，官方網頁作一致性檢查；
- 司法院普通裁判：解析官方搜尋頁取得 JID，再直接由官方 `data.aspx` 取得並解析全文；
- 憲法法庭：判決、實體裁定、舊制解釋及可取得的個別意見。

第一版不承諾完整歷史法規版本、普通裁判全域召回率、所有程序裁定或完整審級關係。詳見 [Official Providers](docs/OFFICIAL_PROVIDERS.md)。

## Final decision

- `validated`：來源、角色、時點與 claim support 通過；
- `qualified`：草稿有已驗證證據，但召回覆蓋有明示限制；
- `blocked`：不可展示草稿，只回 blockers。

精確查到來源不等於答案已驗證。Final answer 仍必須通過 `validate_legal_answer`。

v0.6.2 的核心法律主張必須以 `claim_bindings` 綁定同一 run 的 evidence ID。只傳 `answer_text` 的舊 caller 會標示 `binding_mode=legacy_unbound`，未綁定核心主張不得進入 `validated`。驗證方法為 `deterministic_grounding_v2`，包含中文 2–4 gram、否定、例外、法條／數字 anchor 與角色規則；這不是 semantic entailment（語義蘊含）。

## Claim Grounding 與 Trust Gate

ALR-TW 分開判斷「找到資料」「來源可信」與「內容支持主張」：

| Source tier | 用途 | 可直接作 final citation |
|---|---|---|
| `official` | 自官方來源取得並固定的內容 | 是，但仍須通過時點、角色與 claim support |
| `verified_cache` | 由受治理 resolver 核對 identifier 與 content hash 的快取 | 有條件 |
| `staging` | 匯入、清洗或 audit 中的候選資料 | 否 |
| `external_semantic_recall` | TLR 或其他外部語意召回結果 | 否 |
| `synthetic` | demo／test fixture | 否 |
| `unknown` | 身分或來源不明 | 否 |

沒有 final citation、來源無法驗證、時點不明、角色錯置、claim 超出證據、只找到 candidate-only 來源，或裁判覆蓋不足卻作無保留結論時，trust gate 都應 fail closed。

## Retention 與 purge

預設 managed SQLite 位於 `~/.cache/alr-tw`，保存 `24h`，上限 `7d`。單次 run 可設定 `retention: "ephemeral"`，在 final validation 後同步刪除。

```bash
alr-tw purge --run RUN_ID --confirm
alr-tw purge --all --confirm
```

清除本機資料不能撤回已傳送給外部服務的查詢或伺服器日誌。詳見 [Storage and Purge](docs/STORAGE_AND_PURGE.md)。

## MCP Client 快速設定

先用安全的 `synthetic` 模式確認 MCP server：

```json
{
  "mcpServers": {
    "alr-tw": {
      "command": "alr-tw-mcp",
      "env": {
        "ALR_TW_DATA_MODE": "synthetic"
      }
    }
  }
}
```

建議依序建立 run、按 `next_operation` 推進研究、依 server-owned evidence 起草，再呼叫 `validate_legal_answer`。只有 `validated` 或規則允許的 `qualified` 結果才可呈現；`lookup_legal_source` 不能取代答案層級的驗證。

## 驗證

```bash
uv run ruff check .
uv run mypy src
uv run pytest -q
python3 scripts/check_no_forbidden_files.py
python3 scripts/check_public_boundary.py
uv build
```

## 公開／私有邊界

公開 repo 保留 provider／resolver interfaces、source tier、evidence promotion、citation policy、MCP schemas、privacy、retention、purge、fail-closed rules、synthetic fixtures、tests、CI 與文件。

Repo 不包含 production corpus、永久官方全文 cache、真實使用者紀錄、私有 eval、向量 shard、credential、私有 endpoint、內部 ranking／chunking 參數或未匿名化案件資料。Synthetic data 只能用於 demo／測試，不能描述為現行法。

## 如何接入真實資料

```text
Choose data mode
  -> configure retention and secrets outside the repo
  -> run alr-tw doctor --live
  -> retrieve candidate sources
  -> resolve official identifier and content
  -> create server-owned evidence snapshot
  -> validate draft claims and citations
  -> present or fail closed
```

- 法規：以法務部官方資料作 authority layer，明確名稱與條號優先 exact lookup；歷史版本不明時 blocked 或轉人工審查。
- 普通裁判：不使用司法院 API；直接解析裁判書搜尋頁取得 JID，再從官方全文頁下載內容。搜尋失敗、網站阻擋、解析失敗與查無資料不得混為同一狀態。
- TLR：[TLR](https://github.com/aa0101181514/tw-legal-rag)只提高普通裁判 candidate recall；命中後仍須回司法院官方來源驗證。`mcp-taiwan-legal-db` 只是公開行為參考，不是 dependency，相關 provider、transport、parser 與 evidence pipeline 均為獨立實作。
- 憲法材料：保留主文、理由、協同意見與不同意見的角色差異，個別意見不能冒充多數理由。

## 重要文件

- [架構](ARCHITECTURE.md)
- [資料政策](DATA_POLICY.md)
- [安全說明](SECURITY.md)
- [信任模型](docs/TRUST_MODEL.md)
- [工具契約](docs/TOOL_CONTRACT.md)
- [TLR Provider](docs/TLR_PROVIDER.md)
- [官方 Providers](docs/OFFICIAL_PROVIDERS.md)
- [Storage and Purge](docs/STORAGE_AND_PURGE.md)
- [Agent Client Guide](docs/AGENT_CLIENT_GUIDE.md)
- [Error Codes](docs/ERROR_CODES.md)
- [Threat Model](docs/THREAT_MODEL.md)
- [Release Notes](docs/RELEASE_NOTES.md)
- [v0.6.2 Release Audit](docs/V062_RELEASE_AUDIT.md)
- [Changelog](CHANGELOG.md)

## 法律聲明

本專案僅供軟體架構、研究與測試，不構成法律意見、律師服務或任何個案結論，也不保證法律資料完整、正確、即時或適用。
