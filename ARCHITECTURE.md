# Architecture

ALR-TW v0.10.0 將「agent 決定如何推理」與「server 決定何者可信」分開。外部 agent 可以提出查詢、逐步呼叫工具、提交爭點與法源 locator 並起草答案，但不能注入正式證據或跳過 obligations。v0.10.0 將這條邊界做成 agent-neutral interoperability contract，不依賴特定前端專案。

ALR-TW 是獨立的、前端無關且 provider-neutral 的公開法律研究驗證 harness，
以 contract-first 方式提供可公開的 contracts、validators、synthetic fixtures
與 boundary tests。它不綁定特定 agent、資料 provider 或部署環境。

```text
MCP client / external agent
  - capabilities negotiation
  - optional untrusted issue/locator plan
  - optional untrusted LegalAnalysisEnvelope
        |
        v
ResearchService
  - ResearchRun state machine
  - ordered obligations
  - idempotent operations
  - final validation
  - research sufficiency / Coverage v2
  - server-owned finalization and structured refusal
  - explicit core-issue coverage
  - unified multi-branch structural/trust validation
        |
        v
ProviderObligationExecutor
  +--------------------+----------------------+-------------------+
  | OfficialLaw        | OfficialJudgment     | Constitutional    |
  | MOJ JSON + webpage | formal citation/JID  | decisions/rulings |
  +--------------------+----------------------+-------------------+
                            ^
                            |
                  TLR candidate-only recall
                  (hybrid_verified + privacy gate)
        |
        v
SqliteStore
  - runs / obligations / operations
  - source records / evidence spans
  - retrieval candidates / TTL cache
        |
        v
validated | qualified | blocked
```

## Civil-law model

- 法規是主要規範來源，必須保留名稱、條號、現行／廢止與時間限制；
- 普通裁判不是一律等同拘束先例，需保留法院、日期、案號、主文、法院理由與當事人主張角色；
- 憲法法庭主文／理由、協同意見、不同意見分開；
- `as_of_date` 無法完成歷史版本核對時，不用現行條文假裝回答歷史問題；
- counter-authority 以 bounded lexical candidate discovery 加官方驗證表達；尚無 semantic opposition classifier，不得主張全球不存在反面見解或實務一致。
- applicability resolver 只依 server-owned provider metadata 表達特別／普通、
  上位／下位與新／舊來源關係；authority／lineage contract 保存法院、程序與
  上訴／審查鏈；公法 contracts／provider SDK 則提供行政規則、行政解釋、訴願
  與立法資料的可替換介面。三者均為結構／信任驗證，不執行語義涵攝。

外部 client 可以拆解請求權基礎、構成要件、抗辯、舉證責任、程序前提、
法律效果與時點爭點；這些仍是 proposal。Server 必須分別驗證來源真實性、
角色、效力與 claim support，不因前端推理看似完整就授予 evidence 資格。

`LegalAnalysisEnvelope` 以 `analyses` 清單承載至多六個不可重複且可併用的
分支：民法、民事程序、刑法、刑事程序、行政法與憲法審查。民法分支區分
請求權成立、權利阻卻、權利消滅、抗辯、責任減輕及救濟計算，保存逐要件
舉證責任；行政法分支內再以 `legality`／`remedy` 區分合法性與救濟軌。
Client 提出的 `met`／`not_met` 不具權威；只有綁定 server-owned normative
source 以及 fact 或 eligible evidence，且 temporal／authority／validity
context 全部通過，才可通過結構與 trust validation。這仍不等於語義涵攝
正確。

## Trust boundaries

1. Caller boundary：caller arguments、answer text 與 source-tier metadata 均不可信。
2. Plan boundary：外部 issue／locator plan 固定為 `untrusted_client_proposal`。
3. Analysis boundary：外部多分支 analysis 固定為
   `untrusted_client_proposal`。
4. External recall boundary：TLR 只產生 candidate，查詢先經本地 privacy gate。
5. Official boundary：HTTPS allowlist、timeout、size/schema checks、server-owned
   evidence freshness 與 expiry；provider snapshot receipt 由 receipt-aware
   adapter 選擇性簽發。
6. Legislative locator boundary：立法院 connector 只可 optional、read-only、bounded
   地回傳 candidate-only locator；ID20、ID19、ID46、ID8、ID48 的程序材料不可直接
   取代正式公布法版本、有效法條或單一立法者意旨，PDF／DOC 連結不解析。
7. Storage boundary：只有 server-owned source/evidence 能進 final validation；秘密不持久化。
8. Presentation boundary：`ready_for_draft` 只代表 workflow completion；由
   research sufficiency、answer mode 與 finalization 決定是否可進入起草
   (`safe_to_draft`)。Finalization 不授權呈現 answer body；只有
   `validate_legal_answer` 的 `validated`／`qualified` 結果可展示，
   `refusal_only`／`blocked` 必須移除草稿。

## Compatibility

`alr_tw.*` 是 v0.10.0 中立 contracts、providers、research 與 storage 的主命名空間。`tw_legal_rag_mcp.*` 保留 legacy synthetic／trace 工具並承載 MCP stdio server。兩者共用 source tier 與 fail-closed invariants；新功能不得反向依賴 client-controlled provenance。Legacy answer／provider-promotion 邊界收到的 raw citation mappings 固定視為 caller-controlled，metadata-only answer helper 不具有答案呈現授權能力。

## v0.10.0 changes

本版新增 Agent Experience 與立法院 connector 契約。詳見
[Agent Client Guide](docs/AGENT_CLIENT_GUIDE.md)
與可複製的 [templates/AGENTS.md](templates/AGENTS.md)。

### Profile-gated MCP catalog

MCP tool catalog 是 discovery 與 invocation 共用的單一分類來源：

| Profile | Exposure |
|---|---|
| `verified` | `server_owned` only |
| `compatibility` | `server_owned` + `legacy_compatibility` |
| `demo` | all catalog entries, including `synthetic_demo` |

`official_only`／`hybrid_verified` 預設 `verified`，`synthetic` 預設 `demo`；
`ALR_TW_MCP_TOOL_PROFILE` 可明示選擇，未知值在 session startup fail closed。Profile
在啟動時固定，`tools/list` 與 `tools/call` 使用相同 gate；被隱藏的工具直接呼叫也
只會得到 `TOOL_NOT_AVAILABLE_IN_PROFILE`，不會繞過 discovery gate。

Agent-neutral tool selection remains small and deterministic at the contract level：

| Intent | First tool |
|---|---|
| Single formal authority lookup | `lookup_legal_source` |
| Multi-step research | `research_legal_question` + `continue_legal_research` |
| Analysis envelope validation | `validate_legal_analysis` |
| Answer validation | `validate_legal_answer` |
| Synthetic demo／CI | Synthetic demo catalog tools only; never for real cases |

這是導流與 runtime gate，不保證任意模型都能正確選擇工具。

### Optional Legislative Yuan locator connector

connector 只是一個 optional、read-only、bounded、candidate-only 的 locator layer。
它可從官方開放資料取得結構化候選，但不解析 linked PDF／DOC，也不宣稱 live
production ready：

| Dataset | Role |
|---|---|
| `20` | 議案提案 locator；不直接提供立法理由正文 |
| `19` | 條文對照表 locator |
| `46` | 委員會議案 locator |
| `8` | 黨團協商 locator |
| `48` | 三讀通過議案 locator |

所有結果仍是 candidate，需回到 server-owned official verification、snapshot／
metadata binding 與 source promotion。沒有正式公布版本時維持 `qualified`；立法
資料不能被當成有效法條，也不能被壓縮成單一立法者意旨。

## Operational limits

本 repo 不包含 production corpus、永久官方快取、向量 shard、LLM、私有
ranking 參數、private manifests、operator state、gold labels 或使用者資料。
Live providers 是有界即時查詢，不保證外部服務可用或全域完整召回。

Snapshot receipt 是 provider-neutral 的公開契約，不是內建 provider 已簽發的
runtime 保證。v0.10.0 內建 `ResearchService` 尚未注入或持久化 live-provider
generation receipt；因此服務端 finalization 最多為 `conditional`／`qualified`。
`ordinary` 只保留給自行接入 receipt-aware provider adapter 並完成 server-owned
同 run receipt binding 的部署。
