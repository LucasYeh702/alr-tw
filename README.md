# ALR-TW：台灣法律 Agentic RAG / MCP Harness

[繁體中文](README.zh-TW.md) | [English](README.en.md)

ALR-TW v0.6.2 是台灣法律研究安全 harness 的官方網頁相容性修正版。它讓外部 agent／LLM 透過 MCP 建立研究 run，但把資料來源、研究步驟、證據升格、答案驗證與清除權限留在 server 端。設計採台灣大陸法系視角：法規時點優先，普通裁判依審級與案件角色處理，憲法法庭多數意見與個別意見分離。

本專案已整合並在 `hybrid_verified` 模式使用 [TLR（Taiwan Legal RAG）](https://github.com/aa0101181514/tw-legal-rag)進行普通裁判候選召回，再由 ALR-TW 回到司法院官方來源驗證。TLR 不會被直接當成正式引用來源。

本專案不是法律意見服務，也不是完整法律資料庫。它提供可安裝的工程框架、官方 provider、TLR 候選召回、SQLite 短期研究狀態、MCP tools、deterministic trust gates 與 synthetic tests。

本 repo 不包含 LLM，也不包含 agent 實作。規劃、工具選擇與自然語言推理由外部呼叫端提供；ALR-TW 只負責可稽核工具與確定性閘門。Repo 內的示範 ranking 參數僅供測試，不是 production ranking 設定。

> v0.6.2 仍是 `0.x` 預覽版本。任何答案仍須由具資格的人員依官方原文、時點與個案事實複核。

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

v0.6.2 提供的主要能力包括：

- query understanding：正規化問題、辨識法律引用及研究限制；
- privacy screen：在查詢可能送往 TLR 前先檢查敏感資訊；
- source planning：分開處理法規、普通裁判與憲法材料；
- candidate recall：以官方搜尋或 TLR 找出候選來源，但不提前授予引用資格；
- exact lookup：支援法規名稱＋條號、憲法裁判字號、完整 JID 與正式裁判字號；
- official verification：回查官方識別碼、官方 URL 與內容，形成不可由 caller 偽造的 evidence snapshot；
- legal-time checks：保存來源取得、驗證、到期與法規版本狀態；
- role-aware analysis：區分法院理由、主文、當事人主張、案件事實及個別意見；
- counter-authority coverage：誠實揭露公開版尚未實作系統性反方裁判搜尋，不會把未搜尋標成已完成；
- deterministic grounding v2：以 explicit claim-to-evidence bindings、中文 2–4 gram、否定、例外、法條／數字 anchor 與角色規則逐項檢查；這不是 semantic entailment（語義蘊含）；
- resumable run：研究義務、候選、證據及 tool events 可在短期 SQLite 中恢復；
- deterministic finalization：最終是否可呈現由 server 規則決定，不由模型自行宣告。

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

## v0.6.2 MCP tools

| Tool | 用途 |
|---|---|
| `research_legal_question` | 建立 server-owned research run，不生成答案 |
| `continue_legal_research` | 以 `operation_id` 執行一個下一步 obligation |
| `get_legal_research_state` | 唯讀取得狀態，不做網路請求、不延長 TTL |
| `lookup_legal_source` | 精確查詢法規條文、憲法字號、JID 或正式裁判字號 |
| `validate_legal_answer` | 只用該 run 的 server-owned evidence 驗證草稿 |
| `purge_research_storage` | 同步刪除單一 run 或全部 managed storage |

舊版 synthetic／trace tools 暫時保留相容性，但新整合應優先使用上述研究服務。

支援的 MCP protocol versions：`2025-11-25`、`2025-06-18`、`2025-03-26`、`2024-11-05`。不支援的版本會在 initialize 階段拒絕。

每個 tool result 都使用固定 envelope：

```json
{
  "ok": true,
  "schema_version": "alr-tw.mcp_tool_result/v1",
  "data": {},
  "error": null
}
```

`request_id`／`client_id` 只用於關聯紀錄，不是 authority 或冪等依據。會改變狀態的操作必須使用 `operation_id`；相同 operation 與相同輸入應取得相同結果。未知欄位、不支援的 protocol version、caller 自帶的 trust decision 或不合法的 purge 請求都會被拒絕。

Codex 等 MCP host 可在 `params._meta` 或 direct `arguments._meta` 放置保留 metadata；server 會在嚴格業務參數驗證前只抽離這兩個位置。其他未知業務欄位仍會被拒絕，`_meta` 原始內容不進入 SQLite、一般 log 或 hash。

## 研究流程

標準 run 依序處理 query understanding、privacy screen（只限 hybrid）、law research、judgment recall、official verification、counter-authority limitation、time context、evidence sufficiency 與 final validation。每次 `continue_legal_research` 只執行一個 obligation，方便 agent 觀察、重試與稽核。

Final decision：

- `validated`：來源、時點、角色與 claim support 通過；
- `qualified`：已驗證來源足以支持草稿，但普通裁判召回等覆蓋有明示限制；
- `blocked`：不可展示草稿，回傳 blockers 而不回 answer body。

`lookup_legal_source` 只證明來源查得，不代表任何答案 claim 已被驗證。

## Claim Grounding 與 Trust Gate

Retrieval candidate 不等於 final citation。ALR-TW 把「找到資料」「來源可信」「內容支持主張」分成三個不同判斷：

| Source tier | 用途 | 可直接作 final citation |
|---|---|---|
| `official` | ALR-TW 自官方來源取得並固定的內容 | 是，但仍須通過時點、角色與 claim support |
| `verified_cache` | 由受治理 resolver 重新核對 identifier 與 content hash 的快取 | 有條件 |
| `staging` | 匯入、清洗或 audit 中的候選資料 | 否 |
| `external_semantic_recall` | TLR 或其他外部語意召回結果 | 否 |
| `synthetic` | demo／test fixture | 否 |
| `unknown` | 身分或來源不明 | 否 |

Trust gate 會在下列情況 fail closed：

- 沒有可用的 final citation；
- citation 不存在、已過期、識別不一致或無法回到官方來源；
- 只有 TLR、staging、synthetic 或 unknown candidate；
- 歷史法規時點或效力狀態無法確認；
- 把當事人主張、案件事實、協同／不同意見誤作法院多數理由；
- claim 缺少證據、超出證據範圍、與證據衝突或仍待人工判斷；
- 普通裁判或反方權威覆蓋不足，卻嘗試作無保留結論。

`validated` 只代表該 draft 在該 run 的 server-owned evidence 與公開規則下通過；它不是對法律意見正確性的保證，也不能取代專業複核。

## Retention 與清除

預設短期 SQLite 儲存位置為 `~/.cache/alr-tw`，預設保留 `24h`，上限 `7d`。單次 run 可用 `retention: "ephemeral"`，在 final validation 後同步清除。

```bash
alr-tw purge --run RUN_ID --confirm
alr-tw purge --all --confirm
```

CLI 與 MCP 共用同一 purge 實作。清除本機資料無法撤回已傳送給外部服務的查詢或其日誌。詳見 [Storage and Purge](docs/STORAGE_AND_PURGE.md)。

## MCP Client 快速設定

先用安全的 `synthetic` 模式確認 client 能啟動 MCP server：

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

建議的 agent 呼叫順序：

1. `research_legal_question` 建立 run；
2. 按 `next_operation` 呼叫 `continue_legal_research`；
3. 必要時用 `get_legal_research_state` 唯讀恢復狀態；
4. 外部 agent 只依 run 中已升格的 evidence 起草；
5. 以 `claim_bindings` 將每個核心主張綁到同一 run 的 evidence ID，再送進 `validate_legal_answer`；
6. 只有 `validated` 或規則允許的 `qualified` 結果才可呈現；
7. 依 retention policy 清除 run。

若只需要核對一個精確法源，可使用 `lookup_legal_source`，但不能跳過答案層級的 `validate_legal_answer`。

最終驗證使用 span-level binding。只有 `answer_text` 的舊 caller 仍可呼叫，但會回傳 `binding_mode=legacy_unbound`；未綁定的核心法律主張不得進入 `validated`。範例：

```json
{
  "run_id": "run_demo",
  "answer_text": "法院認為調動命令仍須符合權利濫用禁止原則。",
  "operation_id": "validate_demo_1",
  "claim_bindings": [
    {
      "claim_id": "claim-1",
      "claim_text": "法院認為調動命令仍須符合權利濫用禁止原則。",
      "claim_type": "court_view",
      "importance": "core",
      "evidence_ids": ["ev_src_demo_section-003"]
    }
  ]
}
```

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

公開 repo 保留的是可重現的工程契約：

- provider 與 resolver interfaces；
- source tier、evidence promotion 與 citation policy；
- server-owned research state、MCP schemas 與 error codes；
- privacy、retention、purge 與 fail-closed 規則；
- synthetic fixtures、tests、CI 與公開文件。

不公開的 production 資產包括真實 corpus、永久 cache、向量資料庫、真實查詢與答案、credential、私有 endpoint、內部 ranking／chunking 參數及未匿名化案件資料。

## 如何接入真實資料

v0.6.2 已提供官方 live providers 與 TLR clean-room adapter。建議部署順序如下：

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

### 法規

法規應以法務部官方資料為 authority layer。明確法規名稱與條號優先走 exact lookup；語意搜尋只能協助探索候選。涉及行為時法、修法或過渡規定時，若對應日期的版本無法確認，系統應 blocked 或要求人工審查。

### 普通裁判

普通裁判不從司法院 API 取得。ALR-TW 直接解析司法院裁判書搜尋頁取得候選與 JID，再由官方全文頁下載內容。搜尋失敗、網站阻擋、解析失敗與查無資料是不同狀態；系統不會把網路或 WAF 問題改寫成「裁判不存在」。

### TLR

[TLR](https://github.com/aa0101181514/tw-legal-rag)用於提高普通裁判 candidate recall。其 excerpt、citation URL、排序或 bundle metadata 都不能自行成為正式證據。只有回到司法院官方來源、識別一致且內容驗證成功後，ALR-TW 才會建立新的 official evidence。`mcp-taiwan-legal-db` 只是公開行為參考，不是 dependency；本專案的 provider、transport、parser 與 evidence pipeline 均為獨立實作。

### 憲法材料

憲法法庭資料應保留主文、理由與個別意見的角色差異。協同意見與不同意見可作研究材料，但不能在沒有標示的情況下作為多數意見或裁判拘束內容。

## v0.6.2 發布說明

v0.6.2 在既有安全邊界上補強舊式 `hlExportPDF?type=JD&id=...` 裁判頁、官方搜尋結果頁 fallback、今日現行法日期語意與 TLR 候選本地相關性重排；但不宣稱支援所有法院格式、自然語言法規議題規劃、完整語義蘊含或系統性反方裁判搜尋。

## 文件

- [Architecture](ARCHITECTURE.md)
- [Architecture Contract](docs/ARCHITECTURE_CONTRACT.md)
- [Trust Model](docs/TRUST_MODEL.md)
- [Tool Contract](docs/TOOL_CONTRACT.md)
- [TLR Provider](docs/TLR_PROVIDER.md)
- [Official Providers](docs/OFFICIAL_PROVIDERS.md)
- [Storage and Purge](docs/STORAGE_AND_PURGE.md)
- [Agent Client Guide](docs/AGENT_CLIENT_GUIDE.md)
- [Error Codes](docs/ERROR_CODES.md)
- [Threat Model](docs/THREAT_MODEL.md)
- [Release Notes](docs/RELEASE_NOTES.md)
- [v0.6.2 Release Audit](docs/V062_RELEASE_AUDIT.md)
- [Security](SECURITY.md)
- [Changelog](CHANGELOG.md)

## 法律聲明

本專案僅供軟體架構、研究與測試，不構成法律意見、律師服務或任何個案結論，也不保證資料完整、正確、即時或適用。
