# ALR-TW：台灣法律 Agentic RAG / MCP Harness

繁體中文 | [English](README.en.md)

ALR-TW v0.11.0 是台灣法律研究安全 harness 的 agent-neutral public preview。外部 agent／LLM 可透過 MCP 建立研究 run、提出爭點與法源 locator；來源取得、研究義務、證據升格、答案驗證與清除則由 server 掌控。架構採台灣大陸法系角度：現行法規與法律時點優先，普通裁判依審級及段落角色處理，憲法法庭多數理由、協同意見與不同意見分離。

本專案已整合並在 `hybrid_verified` 模式使用 [TLR（Taiwan Legal RAG）](https://github.com/aa0101181514/tw-legal-rag)尋找普通裁判候選，再由 ALR-TW 回查司法院官方全文；TLR provider 也可召回 typed 行政函釋候選，以及有界分頁讀取裁判長全文。所有 TLR 結果本身都不是正式引用證據。

對同一 research run 內已驗證的裁判，也可使用 `inspect_judgment_lineage`
讀取 TLR 資料庫記錄的上、下級審候選，再由目前設定的官方裁判 provider
逐件驗證正文與主文結果。

本專案不是法律意見服務，也不是完整法律資料庫。

本 repo 不包含 LLM，也不包含 agent 實作。規劃、工具選擇與自然語言推理由外部呼叫端提供；ALR-TW 只負責可稽核工具與確定性閘門。Repo 內的示範 ranking 參數僅供測試，不是 production ranking 設定。

> v0.11.0 仍是 public preview。答案必須由具資格的人員依官方原文、時點與個案事實複核。

> 目前 `main` 工作樹是 v0.11.0；仍不代表完整 production 法律判斷能力。

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

v0.11.0 提供 query understanding、outbound/output privacy 分離、法規／裁判／
憲法來源規劃、TLR 候選官方升格、partial source 保留、裁判角色分類、
explicit claim bindings、deterministic grounding v2、短期 resumable run、
agent-neutral interoperability 與 deterministic finalization。單一法律分析
信封包含民法、民事程序、刑法、刑事程序、行政法與憲法審查六種可併用
分支；行政法分支內再區分合法性與救濟軌。這不是
semantic entailment（語義蘊含），也不取代專業法律判斷。
applicability resolver 依 server-owned provider metadata 結構化處理特別法／
普通法、上位法／下位法及新舊法時點關係；無法唯一確認時 fail closed，
不宣稱能從法條文字自行完成語義涵攝。authority／lineage contracts 保存
法院層級、程序姿態、上訴／審查鏈與 bounded negative-treatment 結果；
`not_found_in_scope` 不得升格為全球不存在或實務一致。public-law contracts
與 provider SDK 介面涵蓋行政規則、行政解釋、訴願、立法資料、程序／救濟
階段及 server metadata binding；資料 provider 由部署者自備，candidate 與
evidence 仍分離。
公開版目前以最多 4 個 bounded lexical candidate queries、最多 5 件新官方全文回查處理
反方候選；尚無 semantic opposition classifier，不會把未搜尋或 bounded scope
查無結果改寫成「不存在反面見解」或實務一致。

`ready_for_draft` 只代表 workflow completion，不代表研究充分。server 會以
`research_sufficiency`（`sufficient`、`qualified`、`insufficient`、
`retry_required`）、`answer_mode`（`ordinary`、`conditional`、`refusal_only`）
與 finalization contract 決定答案姿態。synthetic fixture 僅供 demo／契約測試，
不能支撐法律答案；counter-authority 目前是 bounded lexical candidate discovery
（最多 4 queries）加官方逐筆驗證（最多 5 件新全文），尚無 semantic opposition classifier。

目前的 v0.11.0 contracts 另提供 optional semantic verifier sidecar、
provider conformance、receipt-aware adapter 與 deployer boundary validator：sidecar
只能 shadow／advisory 回報，provider source／evidence 必須通過獨立 server binding
與 snapshot consistency，部署者自備 corpus、模型、credentials 與 deployment
parameters 不會進入公開套件。這些介面仍是 structural/trust validation，不是
semantic entailment 或法律答案授權。

### Snapshot receipt 與內建 runtime 限制

Provider-neutral snapshot receipt 是公開的 provider 契約與一致性檢查介面，
不表示本套內建 provider 已簽發 receipt。v0.11.0 內建 `ResearchService` 尚未把
live provider 的 snapshot generation receipt 注入或持久化；因此內建服務的
`get_legal_research_finalization`／`get_legal_research_state` 輸出最多是
`conditional`／`qualified`（通常帶 `SNAPSHOT_RECEIPT_MISSING_LEGACY`），不應宣稱
`ordinary`。`ordinary` 僅保留給接入 receipt-aware provider adapter、並將同一
run 的 server-owned receipts 綁定完成的部署。Finalization 只授權進入起草
（`safe_to_draft`），不授權呈現答案；只有 `validate_legal_answer` 的
`validated`／`qualified` 結果可展示。

外部 agent 可以規劃研究與起草答案，但不能自行宣告來源為官方資料、把候選升格成證據，或繞過最終驗證。

## 可選外部整合範例

召回／locator 資料層可由部署者選擇；目前可採下列整合方式：

| 專案 | 可選角色 | 與 ALR-TW 的邊界 |
|---|---|---|
| [TLR（Taiwan Legal RAG）](https://github.com/aa0101181514/tw-legal-rag) | 普通裁判與行政函釋的語意候選召回、裁判全文有界分頁 | 普通裁判可由 `hybrid_verified` 使用；函釋需部署端另接官方 public-law verifier。所有結果固定為 candidate-only |
| `mcp-taiwan-legal-db` 或其他相容法律資料服務 | 外部候選／locator 來源 | 由前端或部署端自行呼叫，再以 `client_assisted` research plan 提交選定 locator；只有 ALR-TW 官方回查後才能建立 evidence |

如果前端已自行呼叫 TLR 或其他資料服務，該次 run 應透過
`client_assisted` research plan 提交選定的 locator，避免 ALR-TW 重複召回。
外部結果一律先視為 candidate；只有完成官方 identity、正文及
source／evidence binding 後才能升格。

亦可透過 `ALR_TW_LOCAL_PORTAL_ROOT` 接入既有相容的唯讀本機裁判資料層；
候選與快取驗證條件見 [Official Providers](docs/OFFICIAL_PROVIDERS.md)。

## v0.11.0 的安全模型

```text
外部 agent 提問／起草
  -> server-owned research obligations
  -> official providers + optional TLR candidate recall
  -> server-owned evidence (optional provider snapshot receipt)
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

## v0.11.0 MCP tools

| Tool | 用途 |
|---|---|
| `get_legal_research_capabilities` | 回傳資料模式、可用 profiles 與固定信任責任 |
| `research_legal_question` | 建立研究 run，不生成答案 |
| `submit_legal_research_plan` | 登錄 client-assisted 的 untrusted 爭點與 locator |
| `continue_legal_research` | 以 idempotent `operation_id` 執行一個下一步 |
| `get_legal_research_state` | 唯讀讀取 run 狀態 |
| `get_legal_research_finalization` | 取得 server-owned 研究充分性、Coverage v2、snapshot receipt 與答案姿態 |
| `lookup_legal_source` | 精確查詢法規、憲法字號、JID／正式裁判字號 |
| `inspect_judgment_lineage` | 對同一 run 已驗證的六段 JID 查 TLR 上下級審記錄，並逐件回查官方主文；可選 1–20 件驗證上限 |
| `lookup_legislative_history` | 在 live mode 明示查詢有界、candidate-only 的立法院資料定位 |
| `validate_legal_analysis` | 驗證單一信封內六種可併用分支、民法逐要件舉證責任、references 與 legal context |
| `validate_legal_answer` | 只用該 run 的 server-owned evidence 驗證草稿 |
| `purge_research_storage` | 清除單一 run 或全部 managed storage |

舊版 synthetic／trace tools 暫時保留相容性。新整合應使用上述 server-owned research flow。
內建 managed `ResearchService` 不保存 server-owned fact records；capabilities
會回報 `managed_fact_state_store_available=false`。未接自有 fact-state
provider 時應綁 eligible evidence ID，caller 自提 fact status 會被阻擋。

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

本專案不承諾完整歷史法規版本、普通裁判全域召回率、所有程序裁定或完整審級
關係。`inspect_judgment_lineage` 只涵蓋 TLR 資料庫記錄及本次官方回查上限；
查無上級審不代表裁判確定，主文結果分類也不等於已比較前後審見解。
詳見 [Official Providers](docs/OFFICIAL_PROVIDERS.md) 與 [TLR Provider](docs/TLR_PROVIDER.md)。

## Final decision

- `validated`：來源、角色、時點與 claim support 通過；
- `qualified`：草稿有已驗證證據，但召回覆蓋有明示限制；
- `blocked`：不可展示草稿，只回 blockers。

精確查到來源不等於答案已驗證。Final answer 仍必須通過 `validate_legal_answer`。

v0.11.0 的核心法律主張必須以 `claim_bindings` 綁定同一 run 的 evidence ID。只傳 `answer_text` 的舊 caller 會標示 `binding_mode=legacy_unbound`，未綁定核心主張不得進入 `validated`。驗證方法為 `deterministic_grounding_v2`，包含中文 2–4 gram、否定、例外、法條／數字 anchor 與角色規則；這不是 semantic entailment（語義蘊含）。

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

建議建立 run、按 `next_operation` 推進研究，只依 server-owned evidence
起草前先呼叫 `get_legal_research_finalization` 讀取 Coverage v2、
`research_sufficiency` 與 `answer_mode`，再呼叫 `validate_legal_answer`。
finalization 只提供起草前姿態；仍須由 `validate_legal_answer` 回傳 final-answer
`validated` 或 `qualified` 才可呈現，`refusal_only` 不得輸出草稿；
`lookup_legal_source` 不能取代答案層級的驗證。

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

公開 repo 保留 provider／resolver interfaces、統一多分支 analysis
validator、source tier、evidence promotion、citation policy、MCP schemas、
privacy、retention、purge、fail-closed rules、synthetic fixtures、tests、CI
與文件。

Repo 不包含 production corpus、永久官方全文 cache、真實使用者紀錄、
私有 eval、向量 shard、credential、私有 endpoint、private manifests、
operator state、gold labels、內部 ranking／chunking 參數或未匿名化案件
資料。Synthetic data 只能用於 demo／測試，不能描述為現行法。

## 如何接入真實資料

```text
Choose data mode
  -> configure retention and secrets outside the repo
  -> run alr-tw doctor --live
  -> retrieve candidate sources
  -> resolve official identifier and content
  -> create server-owned evidence (bind a receipt only when the adapter issues one)
  -> validate draft claims and citations
  -> present or fail closed
```

- 法規：以法務部官方資料作 authority layer，明確名稱與條號優先 exact lookup；歷史版本不明時 blocked 或轉人工審查。
- 普通裁判：不使用司法院 API；直接解析裁判書搜尋頁取得 JID，再從官方全文頁下載內容。搜尋失敗、網站阻擋、解析失敗與查無資料不得混為同一狀態。
- TLR：[TLR](https://github.com/aa0101181514/tw-legal-rag)提高普通裁判及行政函釋 candidate recall，並提供裁判命中片段與有界全文分頁。普通裁判仍須回司法院官方來源，函釋仍須由 ALR-TW 所治理的官方 public-law adapter 驗證；外部 excerpt、全文與效力標記都不建立 evidence。
- 憲法材料：保留主文、理由、協同意見與不同意見的角色差異，個別意見不能冒充多數理由。

v0.11.0 同時提供 provider-neutral applicability、authority／lineage、公法材料
與 provider SDK contracts。這些介面只處理 server-owned metadata、來源角色、
時點、程序及 bounded 關係，不從來源文字推導法律效果，也不執行 semantic
opposition／entailment；部署者仍須自行提供資料 provider，並由 ALR-TW 驗證
source／evidence binding。

## 重要文件

- [架構](ARCHITECTURE.md)
- [資料政策](DATA_POLICY.md)
- [安全說明](SECURITY.md)
- [信任模型](docs/TRUST_MODEL.md)
- [工具契約](docs/TOOL_CONTRACT.md)
- [Agent-neutral interoperability contract](docs/INTEROPERABILITY_CONTRACT.md)
- [TLR Provider](docs/TLR_PROVIDER.md)
- [官方 Providers](docs/OFFICIAL_PROVIDERS.md)
- [Storage and Purge](docs/STORAGE_AND_PURGE.md)
- [Agent Client Guide](docs/AGENT_CLIENT_GUIDE.md)
- [Error Codes](docs/ERROR_CODES.md)
- [Threat Model](docs/THREAT_MODEL.md)
- [Release Notes](docs/RELEASE_NOTES.md)
- [Agentic Harness Acceptance](docs/AGENTIC_HARNESS_ACCEPTANCE.md)
- [Changelog](CHANGELOG.md)

## 法律聲明

本專案僅供軟體架構、研究與測試，不構成法律意見、律師服務或任何個案結論，也不保證法律資料完整、正確、即時或適用。
