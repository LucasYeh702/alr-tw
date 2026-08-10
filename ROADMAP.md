# Roadmap

## Current release: v0.8.0

v0.8.0 是 agent-neutral、provider-neutral 的台灣法律研究驗證 harness，已完成
P0 的研究充分性、Coverage v2、finalization 與公開契約邊界。它不是完整台灣
法律資料庫，也不提供法律意見或 production SLA；真實資料 provider 由部署者
依公開契約自行接入。

已完成的 v0.8.0 P0 能力：

- `workflow_complete`、`research_sufficiency` 與 `answer_mode` 分離；
  `ready_for_draft` 僅表示流程階段，不代表答案可直接呈現；
- Coverage v2 表達 bounded query/time scope、provider scope、partial／error／
  timeout reason codes、`absence_claim_allowed` 與可選 snapshot receipt 參照；
- server-owned deterministic sufficiency evaluator，必要證據不足時產生
  `insufficient/refusal_only`，受限制但可回答時產生 `qualified/conditional`，
  暫時性 provider 錯誤時要求 retry；
- `get_legal_research_finalization`、finalization contract、structured refusal、
  provider snapshot consistency 與答案姿態 gate；
- bounded counter-authority lexical candidate discovery（最多 4 個 queries）加官方逐筆驗證（最多 5 件新全文）。
  `not_found_in_scope` 不得升格為全球不存在反面見解或實務一致；目前沒有
  semantic opposition classifier；
- provider-neutral applicability resolver：以 server-owned source metadata
  結構化處理特別法／普通法、上位法／下位法與新舊法時點關係；不執行
  semantic entailment，無法確認時 fail closed；
- authority／lineage contracts：保存法院層級、程序姿態、上訴／審查鏈與
  bounded negative-treatment provider result；`not_found_in_scope` 不等於全球
  不存在或實務一致；
- public-law contracts 與 provider SDK 介面：涵蓋行政規則、行政解釋、訴願、
  立法資料、程序／救濟階段與 server metadata binding；資料 provider 由部署者
  自備，candidate 與 evidence 仍分離；
- 統一 `LegalAnalysisEnvelope` 六個可併用分支：民法、民事程序、刑法、刑事
  程序、行政法與憲法審查；既有工具與 payload 維持 additive compatibility；
- public-boundary lint 禁止將未公開資料、私有部署細節、secrets 或 production
  參數帶入公開套件。

Provider-neutral snapshot receipt 目前只是公開契約與一致性檢查介面。內建
`ResearchService` 尚未簽發或持久化 live-provider receipt，因此服務輸出最多為
`conditional`／`qualified`；`ordinary` 保留給 receipt-aware provider adapter
完成同一 run 的 server-owned receipt binding 後使用。

## 已知限制

- 不提供 LLM、語義蘊含引擎、法律答案生成器或完整法律資料庫；synthetic data
  只能作 demo／契約測試，不能支撐法律答案；
- 不承諾完整歷史法規版本、普通裁判全域召回率、完整審級關係、所有程序裁定、
  附件或 OCR；
- 不提供複雜涵攝正確性、系統性反面見解分類、全球不存在證明或實務一致判斷；
- applicability resolver 僅依 provider 明示的來源關係與時點 metadata 做結構化
  選擇，不能自行從法條文字推導特別法優先、法律效果、請求權競合或損害合併；
- 證據能力、證明力、刑法三階層、行政裁量與不確定法律概念仍需人工或外部
  專業判斷；專門領域 coverage 由部署者自行提供。

## v0.9：可插拔語義與專門領域

- semantic verifier plugin interface；仍不得宣稱取代律師判斷或自動完成涵攝；
- 刑事、行政及其他專門領域 analysis profiles；
- 律師標註 gold benchmark 與跨領域回歸測試，gold data 不進公開 repo。

歷史版本與逐版變更請見 [CHANGELOG.md](CHANGELOG.md)。目前契約與工具說明請見
[Agent-neutral interoperability contract](docs/INTEROPERABILITY_CONTRACT.md) 與
[Agentic Harness Acceptance](docs/AGENTIC_HARNESS_ACCEPTANCE.md)。

後續功能不得改變 `candidate != evidence`、官方來源驗證、角色不可混用、
`absence_claim_allowed` 的 bounded scope 限制，以及 refusal／blocked 不洩漏
未授權草稿等核心 invariant。
