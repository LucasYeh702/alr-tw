# TLR Provider

ALR-TW v0.12.0 提供可選的 TLR provider（資料提供者），透過 [TLR（Taiwan Legal RAG）公開專案](https://github.com/aa0101181514/tw-legal-rag)的 HTTP API 召回普通裁判與行政函釋候選，並支援裁判長全文的有界分頁讀取。部署者可依需求選擇召回資料層；正式來源與 evidence 仍由 ALR-TW 驗證。

TLR HTTPS 與官方 provider 相同，使用作業系統 trust store（`truststore`），不走
skip-verify，也不改用獨立 CA bundle。裁判搜尋與行政函釋搜尋若回傳超過 requested
top-K 的結果，視為契約違反而 fail closed。

TLR 現為 `CandidateRecallProvider`／`LineageCandidateProvider` 的 reference adapter，
而非核心 executor 的固定依賴。部署者可注入其他相容 candidate backend；正式
source promotion 與 official verification 行為不因 provider 更換而改變。

TLR 回傳的 `doc_id`、`citation_url`、正式字號與 rank 會被正規化為 typed candidate identity。Candidate 先排序、依可得的 canonical JID 去重，再由 ALR-TW 直接回查司法院官方全文；頁面識別碼不一致時以 `CANDIDATE_OFFICIAL_ID_MISMATCH` 阻擋。五段候選只有在官方頁明示相同五段 ID，或唯一提供前五段相符的六段 canonical JID 時，才能升格；TLR snippet 本身始終不可作 claim-support evidence。

`hybrid_verified` quick mode 先呼叫 TLR／相容 candidate provider；只有無可用候選
或 provider 失敗，才退回司法院關鍵詞搜尋。其後最多選五個排序後候選進行 exact
verification。類案結果固定揭露 bounded top-K qualification；mismatch／not-found
或預算截斷另加限制，被淘汰候選不會進入 evidence。若沒有任何候選通過，run
仍 fail closed。

## 角色與資料流

TLR 是 retrieval-only（僅檢索）的高召回候選服務，不是法律答案生成器，也不是 ALR-TW 的最終權威來源。

TLR 只負責外部 semantic candidate recall；ALR-TW 的 counter-authority
coverage 只做 bounded lexical candidate discovery，官方逐筆回查與
finalization 仍由 ALR-TW server-owned gate 掌控。TLR 的查無結果不可主張
全球不存在反面見解，也不代表實務見解一致。

```text
使用者查詢
  -> 本地 privacy gate
  -> safe / redacted_safe 才送出抽象查詢
  -> TLR /v1/search
  -> external_semantic_recall 候選
  -> 司法院官方來源精確回查
  -> server-owned evidence (optional provider snapshot receipt)
  -> final validation
```

已驗證裁判的歷審檢查使用另一條有界流程：

```text
同一 run 的已驗證裁判 JID
  -> TLR /v1/fulltext（只投影 case_history metadata）
  -> upper / lower 歷審候選
  -> 目前設定的官方裁判 provider 逐筆回查正文
  -> 主文分類 + AuthorityLineageContract
  -> qualified 歷審結果
```

TLR 本身不簽發可升格 evidence 的 receipt，因為它固定是 candidate-only。候選經
官方裁判 provider 逐筆驗證並形成 server-owned source／evidence 後，內建
`ResearchService` 才會依同一 run 的精確合格材料集合簽發並持久化
provider-neutral snapshot receipt。receipt 完整且其他閘門均通過時 `ordinary`
才可能可達；receipt 缺失最高為 `conditional`。候選、TLR excerpt 或 caller
receipt 均不能自我認證。

只有 `ALR_TW_DATA_MODE=hybrid_verified` 會啟用外部語意召回。`official_only` 與 `synthetic` 不會將查詢傳給 TLR。

## 候選層級

TLR 結果固定標示為：

- `source_tier=external_semantic_recall`；
- `trust_status=external_candidate`；
- `evidence_eligible=false`；
- 不產生可作 claim support（主張支持）的 evidence span。

TLR 回傳的 excerpt、citation URL、case history 或 bundle 訊息只能協助定位及排序。它們不能直接成為 ALR-TW 正式引用，也不能因欄位名稱看似官方就升格。

## 行政函釋候選召回

`TlrSemanticRecallProvider.search_administrative_interpretations()` 使用
`POST /v1/legal_references/search`，目前接受
`administrative_interpretation` 與 `tax_interpretation` 兩種 TLR 分類。
回傳固定投影為 `PublicLawCandidate`：

- `material_type=administrative_interpretation`；
- `source_role=interpretive_guidance`；
- 保留發文字號、主管機關、日期、provider-reported status、命中片段、
  `fulltext_total_chars` 及片段是否只涵蓋部分全文；
- `sources=[]`、`server_metadata=null`、`coverage_complete=false`；
- 固定帶 `PUBLIC_LAW_CANDIDATES_ONLY`，不允許 scoped absence claim。

TLR 回傳的 `active_verified`、`unknown`、`repealed` 等狀態都只是外部
provider metadata，不是 ALR-TW 的官方效力查證。查無、TLR server-side rejected
candidate，或高相似分數都不能證明函釋不存在、有效或適用。要產生正式 evidence，
部署端仍須把候選字號交給 ALR-TW 所治理的官方 public-law adapter，完成官方
identity、正文、效力、時點與 server metadata binding；本 repo 目前不內附該
行政函釋 corpus／官方 connector。

## 命中片段與長全文分頁

普通裁判搜尋會優先把 TLR `hit_excerpt` 投影為 candidate excerpt，另保留原本的
結構化 `snippet`。兩者都標示為非 evidence；命中片段只協助決定是否值得官方
回查，不能用來斷言法院理由中存在或不存在某段論述。

`read_candidate_fulltext()` 讀取 `POST /v1/fulltext` 的
`excerpt_offset`、`fulltext_total_chars` 與 `fulltext_truncated`。它會依每頁實際
回傳字數續讀，預設最多 6 頁、硬上限 8 頁；到達頁數上限時保留
`next_excerpt_offset`，讓 caller 明確續讀。輸出同時揭露：

- 每頁 offset、回傳字數、全文總字數與截斷狀態；
- 本次合併字數、頁數、下一個 offset；
- `provider_content_complete`（只描述 TLR 本次文本視窗是否從 0 讀完）；
- `evidence_eligible=false`、`official_verification_required=true`、
  `coverage_complete=false`。

即使 `provider_content_complete=true`，也只代表 TLR 的外部候選文本已讀完，不會
建立 `SourceRecord` 或 `EvidenceSpan`。普通裁判正式 evidence 仍由 ALR-TW 回查
司法院官方全文後產生。

## 歷審檢查

`inspect_judgment_lineage` 接受同一 research run 內已由 server 驗證的六段
canonical JID。工具會讀取 TLR `case_history.upper/lower`，預設最多回查 8 件、
上限 20 件關聯裁判，並使用目前設定的官方裁判 provider 驗證每個節點。
因此 TLR 負責提供資料庫記錄的關聯候選，不限定官方正文必須來自哪一種本地
或遠端 adapter；但升格後的 source 仍必須符合 ALR-TW 的 official／verified-cache
與 evidence gate。

目前會從官方主文的明示文字分類：

- `appeal_dismissed`（上訴／抗告駁回）；
- `affirmed`（維持原判決／裁定）；
- `vacated_remanded`（廢棄／撤銷並發回或更審）；
- `vacated_reversed`（廢棄／撤銷並改判或自為判決）。

只有 TLR 上級審項目的 `main_flag` 帶有廢棄標記，且官方上級審主文也分類為
`vacated_remanded` 或 `vacated_reversed`，才會產生 confirmed `reversed`
negative-treatment record。單獨的 TLR metadata、單獨的關鍵字或外部全文都不夠。

這個工具不把歷審鏈等同於見解鏈。它會回傳各裁判的官方 evidence IDs，供後續
比較；但 `semantic_opinion_comparison_performed=false`，不會自行宣稱前後審見解
相同或不同。TLR 沒有列出上級審，也只代表其資料庫目前沒有記錄，固定
`establishes_finality=false`，不能據此主張裁判確定或未上訴。

## 官方驗證

普通法院候選必須解析出可正規化的官方 JID，再由 ALR-TW 直接向司法院裁判書網站的 `data.aspx` 回查全文。官方回查成功後產生的內容快照是新的 `official` source；TLR candidate 本身仍維持候選身分。

官方不存在、已移除、拒絕、解析失敗與網站不可用是不同狀態。TLR 找不到也只代表目前未檢出，不代表裁判不存在。

## 隱私閘門

不得送往 TLR 的內容包括：

- 身分證字號、電話、電子郵件、地址等個人資訊；
- 未公開案件完整事實、私有契約內容或公司內部代稱；
- 訴訟策略、證據弱點、談判底線；
- 規則無法確定是否安全的內容。

結果為 `sensitive` 或 `uncertain` 時，run 會降級為 `official_only`。`redacted_safe` 只使用本地規則遮罩；本版不呼叫另一個雲端模型改寫查詢。

TLR 是外部服務，可能保留伺服器存取紀錄。使用者應先閱讀其當時有效的隱私、日誌與服務政策；ALR-TW 無法控制或刪除外部服務已接收的資料。

## 降級與錯誤

- timeout、HTTP 錯誤、schema 不符或 privacy block：改走 `official_only`；
- 已取得的官方證據仍可使用，但需揭露普通法院召回可能不完整；
- candidate-only：永遠不能通過 final evidence gate；
- API key 只在設定時注入，不寫入 trace、SQLite 或 doctor 輸出。

## 不保證事項

ALR-TW 不保證 TLR 的可用性、完整性、排序、更新速度或資料正確性。歷審工具只
處理 TLR 資料庫記錄且落在回查上限內的關聯，不保證完整審級鏈。TLR 也不替
ALR-TW 保證最終答案、官方現行狀態或引用資格。正式法律研究仍需檢查官方原文、
時點、程序狀態與反方權威。
