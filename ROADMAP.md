# Roadmap

## Current release: v0.9.0

v0.9.0 是 agent-neutral、provider-neutral 的台灣法律研究驗證 harness，已完成
研究充分性、Coverage v2、finalization、歷史法規、裁判語境安全與可插拔 sidecar
契約。它不是完整台灣
法律資料庫，也不提供法律意見或 production SLA；真實資料 provider 由部署者
依公開契約自行接入。

目前 v0.9.0 已具備的核心能力：

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

## v0.9.0：歷史法規、裁判語境安全與可插拔語義

v0.9.0 延續既有 provider-neutral 與 fail-closed 邊界，已補上歷史法規接入、
裁判主文／理由／審級語境分離，以及可替換的語義驗證接縫。它不是自動法律意見
服務，也不把任何外部模型或資料 provider 設為 authority owner。

### P0：核心安全與完整性（已完成）

- 裁判 attribution contract：分離 `current_court`、`lower_court`、`party`、
  `quoted_authority` 與 `unknown` 發話者；無法唯一歸屬時不得升格為
  `court_holding`；
- 主文與理由分離：新增 `DispositionContract`，區分上訴駁回、維持、廢棄發回、
  撤銷改判、部分准許與程序駁回；主文結果不得推導出未經驗證的法律理由；
- 審級與程序 lineage：保存原審／本院／前次發回等有界關係；非本院見解不得因
  出現在最高法院理由段而自動成為 current-court claim support；
- 立法院／官方歷史法規 provider：支援法條版本、公布／施行／廢止日期、修法
  沿革與立法資料，並以 server-owned source metadata、hash、時間與 snapshot
  binding 驗證；立法資料不得直接當成法條本身；
- 增加裁判 attribution、主文結果、審級 lineage 與歷史法版本的合成邊界 fixtures，
  歧義、衝突、timeout 與來源缺漏一律 fail closed。

### P1：可插拔語義與專門領域（已完成）

- semantic verifier plugin interface：插件只能回報 `supports`、`contradicts`、
  `uncertain` 或 `not_evaluated`，不能建立 evidence、改變 source trust 或授權
  `ordinary`／`validated`；
- 六個 `LegalAnalysisEnvelope` 分支補上領域專屬的 elements、defenses、burden、
  procedural posture 與 refusal constraints：民法、民事程序、刑法、刑事程序、
  行政法與憲法審查；
- provider SDK conformance：官方裁判、官方法規、立法資料與外部 candidate provider
  必須通過同一套 source promotion、snapshot、privacy、scope 與 retry contract；
- receipt-aware adapter：只有同一研究 run 的 server-owned provider receipt 完整綁定
  後，才可從 `qualified`／`conditional` 升格為 `ordinary`。

### P2：非必要公開功能（v0.9.0 已完成）

- 語義插件的模型或規則實作維持 optional、sidecar、shadow-first；新增
  semantic sidecar registration 與 validator，但不納入核心 runtime 依賴，也不取代
  人工法律判斷；
- 新增 deployer provider declaration 與 boundary validator。部署者可自行提供完整
  corpus、歷史法規資料、專門領域模板與內部驗證資料；公開契約不包含真實 corpus、
  案件資料、內部 labels、credentials 或 deployment secrets；
- sidecar 與 provider declaration 只有結構／邊界驗證，不能授權 evidence、source
  trust、finalization 或 presentable answer。

v0.9.0 的公開驗收以契約、邊界與安全行為為準；任何內部資料集、模型評測、外部審查
與分數均不屬於公開 capability 或 release 宣示。

歷史版本與逐版變更請見 [CHANGELOG.md](CHANGELOG.md)。目前契約與工具說明請見
[Agent-neutral interoperability contract](docs/INTEROPERABILITY_CONTRACT.md) 與
[Agentic Harness Acceptance](docs/AGENTIC_HARNESS_ACCEPTANCE.md)。

後續功能不得改變 `candidate != evidence`、官方來源驗證、角色不可混用、
`absence_claim_allowed` 的 bounded scope 限制，以及 refusal／blocked 不洩漏
未授權草稿等核心 invariant。
