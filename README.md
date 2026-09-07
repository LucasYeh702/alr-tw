# ALR-TW：台灣法律研究安全 MCP Harness

[繁體中文說明](README.zh-TW.md) | [English](README.en.md)

ALR-TW v0.12.0 是一個讓外部 Agent／LLM 以 MCP 使用台灣法律研究工具的安全框架。它負責管理研究流程、官方來源查證、證據信任邊界、答案驗證與短期資料清除；Agent 負責理解問題與起草文字。

它不是法律意見服務，也不是完整台灣法律資料庫。v0.12.0 仍是 public preview（套件版本 `0.12.0`）；任何輸出都必須由具資格的人員依官方原文、適用時點與個案事實複核。

本 repo 不包含 LLM，也不包含 agent 實作。Repo 內的 demo ranking／示範 ranking 參數只用於展示與測試，不是 production ranking 設定；正式部署的模型、資料集、排序與權重由部署者自行治理。

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
| 多步驟法律研究 | 建立可觀察、可恢復的研究 run；可逐步處理，也可在一次 MCP 呼叫中執行 server-owned obligations。 |
| 候選資料召回 | 使用官方搜尋或 [TLR（Taiwan Legal RAG）](https://github.com/aa0101181514/tw-legal-rag) 找普通裁判／行政函釋候選；正式證據仍由 ALR-TW 官方驗證產生。 |
| 有界歷審檢查 | 對已驗證裁判讀取 TLR 記錄的上、下級審候選，再逐件回查官方正文與分類主文結果。 |
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
- 目前尚無 semantic opposition classifier；有限範圍的反方候選查詢不能證明全球沒有反面見解或實務一致。

當來源時點、角色、內容或主張支持不足時，系統會保留限制、要求人工複核或 fail closed，而不是猜測一個完整答案。

## 研究結果怎麼看

| 結果 | 意義 |
|---|---|
| `validated` | 目前 draft 通過這個研究 run 的確定性來源、時點、角色與 claim 檢查；不等於法律結論必然正確。 |
| `qualified` | 有可核對的證據，但召回範圍、歷史版本、receipt 或其他限制必須一併揭露。 |
| `blocked`／`refusal_only` | 不應展示草稿答案；需要補資料、改變研究範圍或交由人工處理。 |

`ready_for_draft` 只代表研究流程走完，不代表研究充分。最後仍須由
`validate_legal_answer` 決定草稿是否可以展示。

v0.12.0 內建 `ResearchService` 會為同一 run 中通過官方／可信快取閘門的精確
source 與 evidence 集合簽發並持久化 provider-neutral snapshot receipt；caller 提供的
receipt 不受信任。receipt 完整、未過期且其餘閘門均通過時，`ordinary` 才可能
成為起草前姿態；缺 receipt 最高為 `conditional`，混用或內容不符則 fail closed。
`safe_to_draft` 不授權直接展示；仍須由 `validate_legal_answer` 檢查草稿，且
`blocked`／`refusal_only` 不會帶出 answer body。receipt 只證明該 run 的材料綁定，
不證明全域召回完整、裁判確定或實務一致。

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

召回／locator 資料層也可由部署者選擇。若使用 `mcp-taiwan-legal-db` 或其他能提供
正式字號、JID／官方 locator 的相容服務，前端可先取得候選，再透過
`client_assisted` research plan 提交給 ALR-TW；候選仍須完成官方回查才能建立 evidence。

部署環境也可用 `ALR_TW_LOCAL_PORTAL_ROOT` 接入既有相容的唯讀本機裁判資料層；
候選搜尋、快取驗證條件與官方回查方式見 [Official Providers](docs/OFFICIAL_PROVIDERS.md)。

啟用 `hybrid_verified` 時，通過 privacy gate 的查詢文字可能送往 TLR。不要輸入個人秘密、未公開案件事實、私有契約、訴訟策略、證據弱點或談判底線。

### 快速模式（v0.12）

若主要目的是找裁判，可以直接在提示詞開頭指定：

```text
/quick 請查找定型化契約條款效力的相關裁判
```

也可寫成 `快速模式：問題`，或使用
`constraints.research_depth="quick"`。建議搭配 `execute_legal_research`，由 server
在一次呼叫內完成候選召回與最多五件官方回查。`hybrid_verified` quick 會先用
TLR／相容 provider 找候選；只有沒有可用候選或候選 provider 失敗時，才退回司法院
關鍵詞搜尋。候選 JID／正式字號仍逐件回查官方全文。

快速模式縮減的是研究廣度：裁判型問題預設不展開 counter-authority、歷審鏈或
未明示的法規研究；它不會跳過 JID／正式字號與官方內容驗證。至少一件候選通過
後，整條類案查詢仍只能以 `qualified`／`conditional` 呈現已驗證的 bounded
top-K 範圍；候選未通過或超出預算時再附個別限制，`0` 件通過仍會拒答。任何草稿
最後仍須經 `validate_legal_answer`。

研究尚未完成或被 gate 擋下時，`get_legal_research_state` 會提供正式
`research_brief`：只包含已驗證來源 locator、義務進度、blocker 與可重試步驟，沒有
草稿結論，且固定 `answer_authorized=false`、`safe_to_present=false`。Client 不需要為了
顯示進度而繞過 server 直接讀庫。

### 目前來源的角色

| 來源 | 可以協助的工作 | 不能直接宣稱的事情 |
|---|---|---|
| 法務部全國法規資料庫 | 法規名稱、條文、現行／廢止狀態與官方內容核對 | 未確認歷史日期的完整版本、地方自治法規或所有附件 |
| 司法院裁判書網站 | 普通裁判候選、JID 與官方全文回查 | 全域裁判召回、所有程序裁定或完整審級關係 |
| 憲法法庭 | 判決、實體裁定、舊制解釋及可取得的意見材料 | 把個別意見當成多數理由或拘束內容 |
| TLR | 提高普通裁判與行政函釋候選召回率；提供裁判命中片段及有界全文分頁 | TLR excerpt、全文、效力標記、排序或 URL 本身不是正式證據 |
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
| 快速找出並核對類案 | 使用 `/quick` 搭配 `execute_legal_research` | 最多回查五件；未窮盡、查無結果與淘汰候選都不能支持全球不存在主張。 |
| 研究一個包含多個爭點的問題 | 使用 standard／deep 的 `research_legal_question` 與逐步研究流程 | `ready_for_draft` 不是「研究已充分」的保證。 |
| 找普通裁判候選 | 使用官方搜尋或 `hybrid_verified` | TLR 只提高召回，最後仍須回司法院官方全文。 |
| 找行政函釋候選 | 使用 TLR provider 的 typed public-law candidate API | 只作定位；須另經 ALR-TW 所治理的官方 public-law adapter 驗證，內建 runtime 目前不附該 connector。 |
| 查已驗證裁判的上下級審 | 在同一 run 使用 `inspect_judgment_lineage` | 只涵蓋 TLR 記錄與本次回查上限；查無上級審不等於裁判確定，也不自動判斷見解是否不同。 |
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

官方 HTTPS provider 預設使用作業系統憑證庫（`truststore`）。`doctor --live` 會實際
檢查法務部、憲法法庭與司法院裁判來源；憑證驗證失敗會以
`OFFICIAL_TLS_VERIFICATION_FAILED` 明示，而不是被誤報成查無資料。

普通裁判查詢不需要司法院 API token；live 查詢的關鍵字、案號與篩選條件會送到官方網站。不要把未公開個案事實或保密資料當成搜尋詞。

## Agent 最短使用流程

新整合建議依序：

1. 呼叫 `get_legal_research_capabilities`，先確認目前 data mode 與可用工具。
2. 快速或一般 server-managed 研究可呼叫 `execute_legal_research`；需要逐步除錯或
   client-assisted plan 時，使用 `research_legal_question` 再依序執行
   `continue_legal_research`。
3. 讀取 `get_legal_research_finalization`，確認證據、限制與答案姿態。
4. 只使用同一 run 的 server-owned evidence 起草。
5. 呼叫 `validate_legal_answer`，只展示允許展示的結果。
6. 依 retention policy 等待自動清除，或使用 `purge_research_storage` 手動清除。

若只需核對單一法源，可使用 `lookup_legal_source`；若要查立法沿革候選，可在 live mode 明示使用 `lookup_legislative_history`。

若本機 stdio MCP process 被強制終止，而宿主畫面仍顯示舊的 connected 狀態，先停用
再啟用該 MCP 設定或重新啟動宿主；仍為 `Not connected` 時移除後依原設定重新加入。
強制終止後的宿主連線顯示不由 ALR-TW process 控制，不應把殘留 UI 狀態視為健康證據。

可複製的 Agent 工作區規則見 [templates/AGENTS.md](templates/AGENTS.md)。它是使用建議，不是安全邊界；真正的工具權限、證據升格與拒答規則由 MCP server 強制執行。

### 主要工具分工

| 工具 | 用途 |
|---|---|
| `get_legal_research_capabilities` | 了解目前資料模式、可用 profile 與 server 的信任責任。 |
| `research_legal_question` | 建立一個 server-owned research run。 |
| `execute_legal_research` | 建立 run 並一次執行可執行的 server-owned obligations；保留逐步稽核與 final-answer validation。 |
| `continue_legal_research` | 執行下一個研究義務；每次只推進一個有界步驟。 |
| `get_legal_research_state` | 唯讀恢復研究狀態，不做新的網路請求。 |
| `get_legal_research_finalization` | 查看研究充分性、覆蓋限制、blockers 與答案姿態。 |
| `lookup_legal_source` | 精確查詢法規、裁判或憲法法庭正式來源。 |
| `inspect_judgment_lineage` | 查同一 run 已驗證裁判的 TLR 上下級審記錄，並回查官方主文。 |
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
