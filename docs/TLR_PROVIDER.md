# TLR Provider

ALR-TW v0.6.2 以 clean-room adapter（淨室轉接器）接入 [TLR（Taiwan Legal RAG）公開專案](https://github.com/aa0101181514/tw-legal-rag)的 HTTP API。實作只依公開 OpenAPI 行為撰寫；未複製 TLR 或其他參考專案的程式碼。

TLR 回傳的 `doc_id`、`citation_url`、正式字號與 rank 會被正規化為 typed candidate identity。Candidate 先排序、依可得的 canonical JID 去重，再由 ALR-TW 直接回查司法院官方全文；頁面識別碼不一致時以 `CANDIDATE_OFFICIAL_ID_MISMATCH` 阻擋。五段候選只有在官方頁明示相同五段 ID，或唯一提供前五段相符的六段 canonical JID 時，才能升格；TLR snippet 本身始終不可作 claim-support evidence。

## 角色與資料流

TLR 是 retrieval-only（僅檢索）的高召回候選服務，不是法律答案生成器，也不是 ALR-TW 的最終權威來源。

```text
使用者查詢
  -> 本地 privacy gate
  -> safe / redacted_safe 才送出抽象查詢
  -> TLR /v1/search
  -> external_semantic_recall 候選
  -> 司法院官方來源精確回查
  -> server-owned evidence snapshot
  -> final validation
```

只有 `ALR_TW_DATA_MODE=hybrid_verified` 會啟用外部語意召回。`official_only` 與 `synthetic` 不會將查詢傳給 TLR。

## 候選層級

TLR 結果固定標示為：

- `source_tier=external_semantic_recall`；
- `trust_status=external_candidate`；
- `evidence_eligible=false`；
- 不產生可作 claim support（主張支持）的 evidence span。

TLR 回傳的 excerpt、citation URL、case history 或 bundle 訊息只能協助定位及排序。它們不能直接成為 ALR-TW 正式引用，也不能因欄位名稱看似官方就升格。

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

ALR-TW 不保證 TLR 的可用性、完整性、排序、更新速度或資料正確性。TLR 也不替 ALR-TW 保證最終答案、官方現行狀態、審級關係或引用資格。正式法律研究仍需檢查官方原文、時點、程序狀態與反方權威。
