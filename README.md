# ALR-TW：台灣法律研究安全 MCP Harness

[繁體中文說明](README.zh-TW.md) | [English](README.en.md)

ALR-TW v0.10.0 是一個讓外部 Agent／LLM 以 MCP 使用台灣法律研究工具的安全框架。它負責管理研究流程、官方來源查證、證據信任邊界、答案驗證與短期資料清除；Agent 負責理解問題與起草文字。

它不是法律意見服務，也不是完整台灣法律資料庫。v0.10.0 仍是 public preview；任何輸出都必須由具資格的人員依官方原文、適用時點與個案事實複核。

## 先看懂 ALR-TW

ALR-TW 的角色不是替 Agent「想出法律答案」，而是把法律研究中容易被忽略的步驟留下紀錄並加上限制：問題理解、來源尋找、官方回查、時點與角色辨識、證據綁定，以及最後的答案驗證。

```text
外部 Agent／使用者提出問題
        ↓
ALR-TW 建立研究狀態與研究義務
        ↓
候選召回 → 官方來源查證 → 證據與時點／角色檢查
        ↓
Agent 依已驗證證據起草
        ↓
答案驗證 → validated／qualified／blocked
```

這種分工讓不同的 Agent、模型或 MCP client 可以共用同一套 server-side trust boundary；但模型本身的推理品質、法律涵攝與個案判斷，仍不會由這個 repo 自動保證。

## 這個專案可以做什麼

| 功能 | 白話說明 |
|---|---|
| 精確法源查詢 | 查詢法規條文、正式裁判字號、JID 與憲法法庭資料，並回到官方來源核對。 |
| 多步驟法律研究 | 建立可觀察、可恢復的研究 run，逐步處理法規、裁判、憲法材料與時點問題。 |
| 候選資料召回 | 使用官方搜尋或 [TLR（Taiwan Legal RAG）](https://github.com/aa0101181514/tw-legal-rag) 找候選裁判，再由 ALR-TW 回查司法院官方全文。 |
| 分析與答案驗證 | 將核心主張綁定同一研究 run 的證據，檢查來源、角色、時點與支持關係。 |
| 立法院資料定位 | 定位提案、條文對照、委員會、黨團協商與三讀階段材料；結果只作立法沿革候選。 |
| 短期研究資料管理 | 保存研究狀態與工具紀錄，依 retention policy 自動到期，也可以手動 purge。 |

## 它不會替你保證什麼

- 不會產生法律意見、律師服務或個案決定。
- 不會把 Agent 自己提供的 official URL、hash、來源角色或 trust metadata 當成官方證據。
- 搜尋結果、TLR 結果、外部網路搜尋與立法院材料都是 candidate；只有 server-owned 的官方驗證結果才能進入正式答案驗證。
- 不承諾指定歷史日期的完整法規版本、普通裁判全域召回率、所有程序裁定正文、完整審級關係或附件／OCR 全覆蓋。
- 立法院連結的 PDF／DOC 不在本 connector 中解析；立法材料不等於現行有效法條，也不能代表單一立法者意旨。
- `not_found` 或有限範圍內查不到，不代表全球不存在，也不代表實務一致。

當來源時點、角色、內容或主張支持不足時，系統會保留限制、要求人工複核或 fail closed，而不是猜測一個完整答案。

## 研究結果怎麼看

| 結果 | 意義 |
|---|---|
| `validated` | 目前 draft 通過這個研究 run 的確定性來源、時點、角色與 claim 檢查；不等於法律結論必然正確。 |
| `qualified` | 有可核對的證據，但召回範圍、歷史版本、receipt 或其他限制必須一併揭露。 |
| `blocked`／`refusal_only` | 不應展示草稿答案；需要補資料、改變研究範圍或交由人工處理。 |

`ready_for_draft` 只代表研究流程走完，不代表研究充分。最後仍須由
`validate_legal_answer` 決定草稿是否可以展示。

## 主要安全邊界

ALR-TW 將「找到資料」、「來源可信」與「資料支持這個主張」分開處理：

1. Agent 可以提出問題、爭點與 locator，但不能自行建立正式 evidence。
2. Server 會從官方來源取得並驗證內容，再建立 server-owned evidence。
3. 法規時點、法院角色、主文／理由、當事人主張與個別意見會分開保存。
4. 證據過期、識別不一致、角色錯置、主張超出證據或覆蓋不足時，結果會降級或拒絕。

因此，`source_tier=official`、caller 自帶的 URL 或「已驗證」欄位都不能繞過 server 的信任閘門。

## 一次研究通常會經過什麼步驟

1. 先確認目前的資料模式、可用工具與限制。
2. 建立研究 run，記錄問題、研究範圍與必要的法律爭點。
3. 依研究義務取得候選法規、裁判、憲法或公法材料。
4. 對候選來源回查官方識別碼與內容；候選資料不會直接升格。
5. 檢查法律時點、來源角色、法院層級、主文／理由與個別意見等差異。
6. Agent 以同一 run 的 evidence 起草，將核心主張綁定到對應證據。
7. 由 `validate_legal_answer` 決定可以展示、必須附限制，或只能拒答。

研究流程可以中斷與恢復；`get_legal_research_state` 只讀取狀態，不會自行發出新的網路請求，也不會延長保存期限。

## 資料模式

| 模式 | 會不會連線 | 適合用途 |
|---|---|---|
| `synthetic` | 不連線 | 預設的離線 demo、CI 與契約測試；不能支撐真實案件答案。 |
| `official_only` | 只連官方來源 | 法規、司法院裁判與憲法法庭的查詢與官方回查。 |
| `hybrid_verified` | 官方來源 + TLR | 用 TLR 提高普通裁判候選召回，再回司法院官方來源驗證。 |

啟用 `hybrid_verified` 時，通過 privacy gate 的查詢文字可能送往 TLR。不要輸入個人秘密、未公開案件事實、私有契約、訴訟策略、證據弱點或談判底線。

### 目前來源的角色

| 來源 | 可以協助的工作 | 不能直接宣稱的事情 |
|---|---|---|
| 法務部全國法規資料庫 | 法規名稱、條文、現行／廢止狀態與官方內容核對 | 未確認歷史日期的完整版本、地方自治法規或所有附件 |
| 司法院裁判書網站 | 普通裁判候選、JID 與官方全文回查 | 全域裁判召回、所有程序裁定或完整審級關係 |
| 憲法法庭 | 判決、實體裁定、舊制解釋及可取得的意見材料 | 把個別意見當成多數理由或拘束內容 |
| TLR | 提高普通裁判候選召回率 | TLR excerpt、排序或 URL 本身不是正式證據 |
| 立法院官方資料集 | 定位提案與立法過程材料 | 有效法條、完整立法理由或單一立法者意旨 |

立法院資料是 optional、read-only、bounded、candidate-only 的定位結果，可涵蓋議案提案、條文對照表、委員會議案、黨團協商與三讀階段材料。只有在 live data mode 中由 Agent 明示呼叫 `lookup_legislative_history` 才會查詢；`synthetic` mode 固定不連線。連結的 PDF／DOC 不在 connector 中解析，材料仍須回到正式公布版本與 server-owned official verification，才可能進一步作為研究證據。

詳細的 provider 行為、解析限制與來源升格規則見 [Official Providers](docs/OFFICIAL_PROVIDERS.md)。

## 資料保存與隱私

研究 run 會暫存在受管理的 SQLite 儲存中，用來保存研究狀態、工具事件與 evidence 關聯；預設位置是 `~/.cache/alr-tw`，預設保留 `24h`，公開預覽的上限為 `7d`。也可以將單次 run 設為 `ephemeral`，在答案驗證後同步清除。

```bash
alr-tw purge --run RUN_ID --confirm
alr-tw purge --all --confirm
```

清除本機資料不能撤回已經送到 TLR、官方網站或其他外部服務的查詢與日誌。不要把 API key、個人資料、未公開案情或秘密寫入 repo、`.env.example`、trace、SQLite 或 MCP client log。完整規則見 [Storage and Purge](docs/STORAGE_AND_PURGE.md) 與 [Data Policy](DATA_POLICY.md)。

## 常見使用情境

| 你想做的事 | 建議方式 | 需要注意 |
|---|---|---|
| 只查一個條文或正式裁判 | 使用 `lookup_legal_source` | 查到來源不等於整份答案已驗證，仍要做 answer validation。 |
| 研究一個包含多個爭點的問題 | 使用 `research_legal_question` 與逐步研究流程 | `ready_for_draft` 不是「研究已充分」的保證。 |
| 找普通裁判候選 | 使用官方搜尋或 `hybrid_verified` | TLR 只提高召回，最後仍須回司法院官方全文。 |
| 查修法背景或立法沿革 | 在 live mode 明示 `lookup_legislative_history` | 結果是 bounded candidate locator，不是有效法條或完整理由全文。 |
| 驗證已經寫好的草稿 | 用同一 run 的 evidence 呼叫 `validate_legal_answer` | 未綁定核心主張、證據衝突或範圍不足時，結果可能被拒絕。 |

## 最短安裝方式

需要 Python 3.11 以上：

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[all]'
```

先以離線模式確認安裝：

```bash
alr-tw doctor
```

要啟用官方 live mode，必須明確選擇資料模式：

```bash
export ALR_TW_DATA_MODE=official_only
export ALR_TW_RETENTION=24h
alr-tw doctor --live
```

普通裁判查詢不需要司法院 API token；live 查詢的關鍵字、案號與篩選條件會送到官方網站。不要把未公開個案事實或保密資料當成搜尋詞。

## Agent 最短使用流程

新整合建議依序：

1. 呼叫 `get_legal_research_capabilities`，先確認目前 data mode 與可用工具。
2. 需要研究時呼叫 `research_legal_question`，再依序執行 `continue_legal_research`。
3. 讀取 `get_legal_research_finalization`，確認證據、限制與答案姿態。
4. 只使用同一 run 的 server-owned evidence 起草。
5. 呼叫 `validate_legal_answer`，只展示允許展示的結果。
6. 依 retention policy 等待自動清除，或使用 `purge_research_storage` 手動清除。

若只需核對單一法源，可使用 `lookup_legal_source`；若要查立法沿革候選，可在 live mode 明示使用 `lookup_legislative_history`。

可複製的 Agent 工作區規則見 [templates/AGENTS.md](templates/AGENTS.md)。它是使用建議，不是安全邊界；真正的工具權限、證據升格與拒答規則由 MCP server 強制執行。

### 主要工具分工

| 工具 | 用途 |
|---|---|
| `get_legal_research_capabilities` | 了解目前資料模式、可用 profile 與 server 的信任責任。 |
| `research_legal_question` | 建立一個 server-owned research run。 |
| `continue_legal_research` | 執行下一個研究義務；每次只推進一個有界步驟。 |
| `get_legal_research_state` | 唯讀恢復研究狀態，不做新的網路請求。 |
| `get_legal_research_finalization` | 查看研究充分性、覆蓋限制、blockers 與答案姿態。 |
| `lookup_legal_source` | 精確查詢法規、裁判或憲法法庭正式來源。 |
| `lookup_legislative_history` | 查詢立法院 candidate-only 立法資料定位。 |
| `validate_legal_analysis` | 驗證結構化分析與 server-owned references。 |
| `validate_legal_answer` | 以同一 run 的 evidence 驗證草稿答案。 |
| `purge_research_storage` | 清除單一 run 或受管理的研究資料。 |

Synthetic demo tools 僅用於離線測試與契約示範，不應用於真實案件或正式法律引證。完整工具清單與 input／output schema 見 [Tool Contract](docs/TOOL_CONTRACT.md)。

## MCP Client 設定範例

先以不連線的 synthetic mode 測試 MCP client：

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

完整 tool schema、錯誤碼、profile、MCP protocol 相容性與資料契約，請看下方技術文件。

## 詳細文件

### 給使用者與 Agent 整合者

- [Agent Client Guide](docs/AGENT_CLIENT_GUIDE.md)
- [可複製的工作區指引](templates/AGENTS.md)
- [Release Notes](docs/RELEASE_NOTES.md)

### 信任、安全與資料邊界

- [Trust Model](docs/TRUST_MODEL.md)
- [Threat Model](docs/THREAT_MODEL.md)
- [Public／Private Boundary](docs/PUBLIC_PRIVATE_BOUNDARY.md)
- [Storage and Purge](docs/STORAGE_AND_PURGE.md)
- [Data Policy](DATA_POLICY.md)

### 來源與介面契約

- [Official Providers](docs/OFFICIAL_PROVIDERS.md)
- [Tool Contract](docs/TOOL_CONTRACT.md)
- [Agent-neutral Interoperability Contract](docs/INTEROPERABILITY_CONTRACT.md)
- [Error Codes](docs/ERROR_CODES.md)
- [Architecture Contract](docs/ARCHITECTURE_CONTRACT.md)

### 驗收與開發

- [Agentic Harness Acceptance](docs/AGENTIC_HARNESS_ACCEPTANCE.md)
- [Release Audit Procedure](docs/RELEASE_AUDIT_PROCEDURE.md)
- [Architecture](ARCHITECTURE.md)
- [Security](SECURITY.md)
- [Changelog](CHANGELOG.md)

## 法律聲明

本專案僅供軟體架構、法律研究與測試，不構成法律意見、律師服務或任何個案結論，也不保證資料完整、正確、即時或適用。
