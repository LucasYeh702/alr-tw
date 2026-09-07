# v0.12.0

套件與 MCP `serverInfo` 版本均為 `0.12.0`，仍是 public preview（公開預覽版）。

v0.12.0 的主軸是 bounded verified quick research（有界、仍經官方查證的快速研究）：
讓使用者用提示詞直接縮小研究廣度，減少 MCP 往返與不必要的延伸查詢，同時保留
候選字號、官方正文與最終答案的查證邊界。

## 新增

- 使用 `/quick 問題`、`快速模式：問題`，或
  `constraints.research_depth=quick` 啟用快速模式。提示詞與結構化設定衝突時
  fail closed（封閉式拒絕）。
- 新增 `execute_legal_research`，可在一次 MCP 呼叫內建立研究 run、依序執行目前
  可處理的 server-owned obligations（伺服器掌控的研究義務），並回傳耗時及有界
  evidence bundle（證據包）。既有逐步研究工具完整保留。
- `hybrid_verified` 的 quick 裁判研究先以 TLR 或相容 provider 召回候選，再對最多
  五件候選逐件查證。唯讀本機官方快取只有在 catalog-bound receipt、coverage
  binding 與 trusted-text／provenance hash gate 全部匹配時，才可由 server 採納並
  投影為 `verified_cache` source／evidence 記錄；candidate-only 快取不會升格。三道
  閘門任一不符時，須以 canonical JID／正式字號回查司法院官方正文。只有沒有可用
  候選，或 TLR／相容候選 provider 失敗時，才退回官方關鍵詞搜尋。TLR 結果本身
  不會成為可引用證據。
- 內建 `ResearchService` 會為同一 run 中符合資格的官方／可信快取材料簽發並持久化
  server-owned snapshot receipt（伺服器持有的快照收據）。receipt 與所有其他閘門
  通過時，`ordinary` 起草姿態才可能到達；caller 自帶 receipt 不受信任。
- 新增 provider-neutral（供應者中立）的 candidate／lineage protocols 與只讀
  `alr-tw verify-provider --input` conformance-envelope（相容性封包）檢查。
  此命令只檢查 caller 提交的結構與欄位關聯，不證明來源、簽發可信 receipt、
  升格 evidence 或授權答案展示。
- 新增 public-safe、gold-free 的 ChronoLex-TW 評測 adapter；套件不內附或自動下載
  資料集，歷史法規版本沒有 evaluator-owned server evidence（評測端持有的伺服器
  證據）時固定為 `not_scoreable`。

## 改進

- 法規記憶體快照到期即重新取得；更新失敗不回退舊資料。重複查詢與網頁複核
  不會替舊快照續期，下載或複核途中到期也不產生可引用證據。
- 發布閘門加入 Python 3.11／3.12 的獨立 TLR 安裝測試，並保留實際套件的
  公開邊界掃描；模擬傳輸測試不代表外部服務連線驗收。

- 大量 evidence 不再因 512-ID 欄位上限造成 state、finalization 或 validation 失敗。
  公開欄位提供 deterministic preview（確定性預覽），完整 passage 集合由伺服器以
  count 與 SHA-256 digest 綁定；核心主張仍須逐筆綁定實際使用的 passage ID。
- `get_legal_research_state` 新增不含答案的 `research_brief`，只回報已驗證來源
  locator、義務進度、blocker 與安全下一步；它固定不授權起草結論或對外展示。
- Counter-authority（反方權威）把長自然語言壓成最多 128 字的法條與爭點詞短查詢；
  有界查無仍不能改寫成沒有反面見解或實務一致。
- 官方 HTTPS transport 改用作業系統憑證庫；`alr-tw doctor --live` 會探測法務部、
  憲法法庭與司法院 provider，憑證錯誤明確 fail closed，沒有略過 TLS 驗證的 fallback。
- 無法解析的外部候選會觸發官方 fallback；provider 身分、資料關聯、privacy receipt
  或 top-K 契約不符時一律 fail closed，錯誤材料不會持久化。
- Evidence bundle 先保留法規與憲法材料，再套用最多五件裁判的預算，避免必要法源
  被裁判數量擠出。
- Quick mode 的純 JID／正式字號也會進入官方回查；與明示
  `include_counter_authority=true` 衝突時拒絕，不會默默省略使用者要求。

## 相容性

- `research_legal_question`、`continue_legal_research`、所有 validation 與 purge 工具
  維持可用；新增工具與欄位採 additive（附加式）設計。
- v0.11 的 `ProviderSet(tlr=...)` constructor slot（建構參數）暫時保留；新整合應改用
  `candidate_recall` 與 `lineage_candidates`。
- 沿用既有 `qualified`／`conditional` 語意，不增加同義答案狀態。
- 新工具 `execute_legal_research` 的 `operation_prefix` 只標記步驟，並非冪等鍵；
  重複呼叫會建立新 run。需要續跑時應使用既有逐步工具。

## 使用限制

- Quick mode 縮減的是研究廣度，不是查證標準。它預設不展開未要求的
  counter-authority、歷審鏈或法規擴張，但不會跳過 JID／正式字號、官方內容或
  `validate_legal_answer`。
- 類案 quick 是 bounded top-K（有界前 K 筆）。至少一件裁判通過官方驗證時，結果
  最高仍是 `qualified`／`conditional`；`0` 件通過則是
  `insufficient`／`refusal_only`。查無或預算截斷不能支持「沒有其他類案」、裁判
  確定或實務一致。
- `execute_legal_research` 的 finalization 只可能授權 `safe_to_draft`；草稿仍須以同一
  run 的 evidence 呼叫 `validate_legal_answer`，只有該工具允許的答案才能展示。
- Snapshot receipt 只證明同一 run 的材料集合與內容綁定，不證明全域召回完整、
  裁判確定、沒有反面見解或法律結論正確。
- 本版仍是 public preview，不提供法律意見、完整台灣法律資料庫或 production SLA
  （正式環境服務水準承諾）；所有輸出仍須由具資格人員依官方原文、適用時點與個案
  事實複核。

完整能力範圍、驗收條件與非目標見
[v0.12.0 Release Scope](V0120_RELEASE_SCOPE.md)。
