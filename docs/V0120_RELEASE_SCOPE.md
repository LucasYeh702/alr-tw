# ALR-TW v0.12.0 Release Scope

v0.12.0 的主軸是把 v0.11 已寫入契約與 profile 的信任邊界，轉成可重跑、可量測
且 fail-closed 的 release gates，並讓內建 receipt-aware 路徑在嚴格條件下真的
可達 `ordinary`。bounded verified quick mode 同時用來量測能縮短多少實際研究
時間，但不降低來源真偽閘門。這份文件描述 v0.12.0 的發布範圍；實際發布以同名
tag 與 GitHub Release 為準，亦不構成 production readiness 聲明。

本版必須同時回答：已知信任邊界攻擊是否被擋且 false-refuse 可量測；內建
`ResearchService` 是否能簽發、持久化並重算同 run receipt；verified profile 是否
能在十分鐘內走完一條通過與一條拒絕路徑。任一項未滿足，不應發布為 v0.12.0。

## 已納入 v0.12.0

### Bounded verified quick mode

- 使用者可在 query 開頭使用 `/quick` 或 `快速模式：`；也可繼續使用結構化的
  `constraints.research_depth=quick`。提示詞與結構化設定衝突時 fail closed。
- 裁判型 quick query 省略未明示的法規擴張、反方見解及歷審鏈；若 query 明示
  「某法第某條」，仍保留法規回查。
- `hybrid_verified` quick 先用 TLR／相容 provider 找候選；沒有可用候選或候選
  provider 失敗時才退回司法院關鍵詞搜尋。最多只選五件回查，每一件都必須以
  canonical JID／正式字號回查司法院；唯讀本機快取僅在 catalog-bound receipt、
  coverage binding 與 trusted-text／provenance hash gate 全部匹配時，才可由 server
  採納並投影為 `verified_cache`。candidate-only 快取不會升格；任一條件不符時仍回
  官方來源。
- `0` 件通過官方驗證仍是 `refusal_only`。類案 quick 固定保留 bounded top-K
  qualification，因此即使入選候選全數通過也只允許 `qualified`／`conditional`；
  失敗碼與截斷另行揭露，不允許推論「沒有其他類案」、裁判確定或實務一致。

### Autonomous MCP execution

- `execute_legal_research` 在一次 MCP 呼叫內建立 run 並順序執行 server-owned
  obligations；既有 `research_legal_question`／`continue_legal_research` 保留，
  供逐步除錯及 `client_assisted` 流程使用。
- 自動流程最多 32 步，預設 12 步；遇 retryable provider 結果即停止，不在單次
  request 內反覆敲擊外部服務。
- 回應包含每一步與整體 `elapsed_ms`。到達 `ready_for_draft` 時附上預設最多十二個
  來源、其中裁判最多五件、每來源最多八段的 server-owned evidence bundle；法規與
  憲法材料不與裁判共用五件 quota。
- 自動流程不執行 final-answer validation。外部 Agent 起草後仍須提供同 run 的
  evidence bindings，交由 `validate_legal_answer` 決定是否可展示。
- 未完成或 blocked run 由 `get_legal_research_state.research_brief` 提供正式非答案
  出口；固定不含結論且 `answer_authorized=false`、`safe_to_present=false`。

### Built-in same-run snapshot receipts

- 官方／可信快取 provider 產生可支援主張且未過期的 source／evidence 後，內建
  `ResearchService` 依 provider 分組，對精確材料集合計算 digest，簽發並持久化
  opaque snapshot receipt。
- receipt 綁定 `run_id`、provider、generation、source version/content hash、
  evidence section/text hash 與 expiry；不保存 raw text 或私有資料層路徑。
- finalization 只讀 server-owned receipt set 並重算目前材料。caller receipt 不可信；
  缺 receipt 最高為 `conditional`，過期、跨 run 或集合不符則 fail closed。
- `ordinary` 只在 receipt 與來源、角色、時點、coverage、privacy 及 evidence gate
  全部通過時可達，而且仍只代表 `safe_to_draft`；`safe_to_present` 必須等草稿通過
  `validate_legal_answer`。

### Deterministic release gates

- **Lane A — 公開紅隊：**固定測試假 official、candidate 當引用、角色錯置、bounded
  查無當實務一致、legacy metadata 繞過，以及只有單邊 treatment marker 的
  confirmed reversal。另用正向公開 fixtures 計算 false-refuse count。
- **Lane B — 內建 receipt：**固定測試簽發與重啟後持久化、缺 receipt 降級、caller
  forged receipt 無效、材料變更未重簽即拒絕，以及 purge cascade。
- **Lane C — 十分鐘路徑：**以 `verified` profile 重跑 capabilities → research →
  continue → finalization → validate；合格條文須通過，假 JID 必須拒絕，blocker
  必須有可理解訊息與 `safe_next_actions`。
- **Lane D — 可選：**歷審雙條件儀表、行政函釋 official port、立法 locator 與
  TLR schema-drift fail-closed 可在不擴張本版主線時納入；未完成不取代 A–C gates。

### Proposal integration

- 新增 provider-neutral `CandidateRecallProvider` 與 `LineageCandidateProvider`
  protocols；TLR 是 reference adapter，v0.11 的 `tlr=` constructor slot 保留相容。
- bounded scope 不再等同全面拒答：已有正式證據的子集合可進入既有
  `conditional` posture；真偽、時點、跨 run 或零 evidence 仍 hard fail。
- `alr-tw verify-provider --input <json>` 提供只讀的 conformance-envelope CLI。
  它只檢查 caller 提交的 common `ProviderResult`、source／evidence 與 receipt
  欄位結構及關聯，不證明來源或簽發可信 receipt；也不掃描部署者的
  SQLite／FTS／graph 資產，不授權 evidence 升格或答案展示。
- ChronoLex-TW adapter 提供 pinned、gold-free、離線評測輸入及 evaluator-owned
  historical-law adjudication；外部資料集不隨套件發布，也不代表已具完整歷史法規
  provider。

完整提議與採納差異見 [proposals/README](../proposals/README.md)。

## 相容性

- 所有既有 step-by-step tools 保留。
- `ResearchRun.max_judgment_verifications` 是 additive 欄位，預設 5，允許 1–5。
- `ProviderSet.tlr` 暫時保留作為 deprecated compatibility slot；新程式應注入
  `candidate_recall`／`lineage_candidates`。
- 既有 `conditional`／`qualified` 語意維持，不新增同義的
  `qualified_advisory` enum，避免不必要的 payload 破壞。

## 發布驗收

1. Lane A 的六類攻擊必須被對應閘門擋下，正向 fixture 的 false-refuse 必須輸出
   可重算 numerator／denominator；「閘門沒擋但法律結論仍可能錯」應列入 RESULTS
   限制，不應偽裝成 deterministic test failure。
2. 內建 official provider 路徑必須簽發並持久化同 run receipt；重啟後仍可讀取，
   caller receipt 不能取代 server set，材料變更、跨 run 或過期必須 fail closed。
3. verified profile 的通過與拒絕端到端路徑各一條，合計須低於十分鐘；拒絕結果
   不得帶 answer body，且 blocker 與 `safe_next_actions` 必須可操作。
4. `hybrid_verified` quick 裁判 query 必須先走 TLR／相容 candidate provider，僅在
   無候選或候選 provider 失敗時退回官方搜尋；仍須 official verification，不得自動
   加入 counter-authority，明示條文時才加入 law research。
5. 回查嘗試不得超過設定值或五件；淘汰候選不得出現在 evidence bundle。
6. 類案 quick 有一件以上官方驗證成功時，finalization 必須是
   `qualified`／`conditional`；`0` 件成功仍是 `insufficient`／`refusal_only`。
7. `execute_legal_research` 必須在 retryable 結果停下、在 client-assisted plan
   尚未登錄時停下，且永遠把 final-answer validation 留給草稿完成後。
8. 全套 lint、typing、test、build、wheel install、MCP stdio smoke 與 public-boundary
   checks 必須在 release candidate tree 上通過；live timing 另列實測，不作 CI SLA。
9. 超過 512 筆 passage evidence 的 state/finalization 不得因契約容量 exception；
   完整集合須以 server-owned digest 綁定，claim validation 仍逐筆查同 run store。
10. Counter-authority query 不得超過官方 provider 的 128 字上限；候選 privacy receipt、
    provider ID、source/evidence 關聯或 TLR top-K 違約時必須 fail closed。

## 實測題目

```text
/quick 請查找定型化契約條款效力的相關裁判
```

應回報候選召回、逐件 JID／正式字號與官方內容驗證、實際驗證件數、截斷狀態、
限制及 elapsed time。若只找到部分可核對裁判，答案應明示「目前已驗證範圍」，
不能把 bounded miss 改寫為不存在。

## 明確非目標

- 不跳過司法院／catalog-bound official-derived exact verification。
- 不把 TLR excerpt、模型記憶、URL 或 HTTP 200 當成證據。
- 不自動宣稱裁判確定、歷審見解相同、全國實務一致或不存在反面見解。
- 不提供法律意見、完整台灣法律資料庫、production SLA 或完整歷史法規 corpus。
- 不把 ChronoLex-TW answer accuracy 當成 live provider、RAG 召回率或法律涵攝品質。
- 不新增 semantic opposition classifier，不把 `not_found_in_scope` 改寫成不存在
  反面見解或實務一致。
- 不把 `inspect_judgment_lineage` 的主文分類宣稱為裁判確定或前後審見解比較。
- 不解析立法院 PDF／DOC，也不把 locator 升格為現行法 evidence。
- 不擴充 `LegalAnalysisEnvelope` 欄位作為本版主線。
