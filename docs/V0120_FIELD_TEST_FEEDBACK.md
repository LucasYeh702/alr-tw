# v0.12.0 MCP client 實測建議與處置

日期：2026-09-04

來源：MCP client 使用 `hybrid_verified` 後提出的匿名化工程建議。本文只保存問題
類型、合成重現方式與 v0.12.0 處置，不保存原始研究題目、案件事實或執行紀錄；
reviewer 主張仍須以本機測試驗證，不直接當成 repository fact。

## 建議摘要

1. **P0 — evidence 粒度與契約容量：**單一裁判可產生超過 3000 個
   `evidence_span`，但 `FinalizationContract.allowed_evidence_ids` 上限為 512。
2. **P0 — counter-authority 長查詢：**整段自然語言研究問題可能超過司法院搜尋輸入
   契約並得到 `INVALID_IDENTIFIER`。
3. **P1 — 未完成 Agent 出口：**`refusal_only` 能阻止答案，但缺少正式、不可誤作
   答案的研究簡報。
4. **P1 — 官方法規 TLS：**certifi 路徑在部分部署無法驗證 `law.moj.gov.tw`，系統
   trust store 可正常連線。
5. **P2 — 法規精確召回：**明示「法規名＋條號」應優先 exact lookup，不應只停在
   keyword candidate。
6. **P2 — stdio 生命週期：**process 被強制終止後，部分 MCP host 可能保留過時的
   connected 顯示。

## 本機確認與 v0.12.0 處置

| 建議 | 本機判斷 | 處置 |
|---|---|---|
| evidence >512 | 已確認，原 builder 會觸發 Pydantic 長度錯誤 | `allowed_evidence_ids` 改為最多 512 筆 deterministic preview；完整 passage set 綁 count + SHA-256 digest，claim validation 仍逐筆讀同 run store |
| counter query 過長 | 已確認，plan 曾允許 500 字、官方 provider 只允許 128 字 | generator v2 產生最多四個、每個最多 128 字的法條＋爭點詞＋相反／不同見解查詢 |
| 缺研究簡報 | 已確認 | 在既有 `get_legal_research_state` additive 加入 `research_brief`；只列 verified locators、進度、blocker、限制與 safe actions，固定兩個 authorization flags 為 false |
| 官方 TLS | 部署模式可重現，舊 transport 使用 httpx 預設 CA bundle | 官方 HTTPS transport 改用 `truststore`；`doctor --live` 實際探測三個官方 provider 並輸出穩定 TLS 診斷碼 |
| 明示法條 exact lookup | 主幹已有 resolver，但一／兩字法規名稱的 planning regex 有缺口 | 修正 regex 並加入民法、刑法、憲法 regression；保留 `client_assisted` 精確 locator 優先說明 |
| stdio host 狀態 | ALR-TW process 無法控制 host UI 的殘留連線狀態 | 文件加入 disable/enable、restart、remove/re-add 的恢復步驟；不宣稱已修復外部 host UI |

第二輪三司會審另補一個直接 regression：即使 completed run 的
`research_brief` 已列出 verified source locator，未提供 passage 級
`claim_bindings` 的核心法律主張仍須 `CLAIM_CITATION_BINDING_REQUIRED` 並維持
`safe_to_present=false`。另以「不公開的非個資 pilot＋明示法條」做 live combined probe，
確認 quick planner 實際保留官方法規 exact lookup，bundle 同時含法規與五件裁判。

## 同輪併入的第一輪 findings

- 不可解析的 TLR／相容 provider 候選不能壓掉官方 fallback。
- Provider `ERROR`、provider ID mismatch 或 source/evidence 關聯不一致的 payload 不得
  進入 storage。
- Candidate privacy receipt 必須符合 typed protocol 並於 runtime 驗證。
- TLR response 超過要求 top-K 時 fail closed。
- Evidence bundle 的五件裁判 quota 不得餓死必要法規／憲法來源。
- `verify-provider` 的 optional collections 若為 JSON `null`，回結構化錯誤而非
  traceback。

最終測試計數、三方 reviewer 身分、共同 prompt hash 與 GO／NO-GO 裁決記錄於
[V0120_THREE_WAY_REVIEW.md](V0120_THREE_WAY_REVIEW.md)。
