# ALR-TW v0.8.0 版本說明

## 新增

- 研究充分性與 Coverage v2：分離 `workflow_complete`、`research_sufficiency` 與 `answer_mode`，並保留 bounded query/time scope、provider scope、reason codes 與 snapshot receipt 參照。
- server-owned `get_legal_research_finalization` 工具與 finalization contract，提供 `ordinary`、`conditional`、`refusal_only` 三種答案姿態、blockers、qualifications 與 safe next actions；答案驗證拒答路徑維持 structured refusal。
- provider-neutral snapshot receipt／consistency contract，避免在同一研究 run 混用無法核對的資料世代。
- 明確區分 provider-neutral receipt 契約與內建 runtime：v0.8.0 內建 `ResearchService` 尚未簽發或持久化 live-provider receipt，因此服務輸出最多為 `conditional`／`qualified`；`ordinary` 保留給 receipt-aware provider adapter 的同 run server-owned binding。Finalization 只表達 `safe_to_draft`，不授權呈現答案；只有 `validate_legal_answer` 的 `validated`／`qualified` 結果可展示。
- bounded counter-authority candidate discovery（最多 4 個 lexical queries、最多 5 件新官方全文回查）與官方驗證結果；`not_found_in_scope` 不表示全球不存在反面見解。
- provider-neutral applicability resolver：以 server-owned metadata 表達特別法／普通法、
  上位法／下位法及新舊法時點關係；解析與驗證需獨立的 server-owned
  `server_source_ids` catalog binding，無法唯一確認時 fail closed。
- authority／judgment-lineage contracts：保存法院層級、程序姿態、上訴／審查鏈與
  bounded negative-treatment provider 結果，不執行 semantic opposition classification。
- public-law contracts 與 provider SDK／adapter 介面：涵蓋行政規則、行政解釋、訴願、
  立法資料、程序／救濟階段及 server metadata binding，資料由部署者自備。

## 變更

- `ready_for_draft` 僅代表研究流程已到可起草階段，不再代表研究充分或可直接回答。
- 最終答案必須依 server-owned research sufficiency、Coverage v2 與 finalization gate 決定；必要證據不足時改以結構化拒答或條件式回答。
- counter-authority 目前僅作 bounded lexical candidate discovery（最多 4 queries）加官方逐筆驗證（最多 5 件新全文），尚無 semantic opposition classifier，不授權實務一致或全球不存在反面見解的主張。
- 舊版研究工具與 payload 維持 additive 相容；舊紀錄可讀回並由伺服器重新計算充分性。
