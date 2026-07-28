# ALR-TW v0.7.1 統一法律分析驗收契約

本文件界定 v0.7.1 可以公開宣稱的法律分析能力與不得擴張的邊界。

## 可宣稱能力

- 單一 `alr-tw.legal-analysis/v1` 信封與 `validate_legal_analysis`；
- `analyses` 可同時承載至多六個不可重複的分支：
  - 民法 `civil_substantive`；
  - 民事程序 `civil_procedure`；
  - 刑法 `criminal_substantive`；
  - 刑事程序 `criminal_procedure`；
  - 行政法 `administrative`；
  - 憲法審查 `constitutional_review`；
- 行政法分支內以 `legality`／`remedy` tracks 區分合法性與救濟；
- 民法分支保存 claims、elements、defenses、逐要件舉證責任與完整法律效果
  taxonomy；
- `complete` scope 必須涵蓋分支核心 dimensions；`issue_limited`、未解決
  issue 與不完整 counter-authority coverage 必須明示 qualification；
- source、evidence、fact、法律時點、authority 與 validity 只能由
  server-owned research context 確認；
- 公開 stateless validator 可接部署者的 server-owned fact-state provider；
  內建 managed `ResearchService` 不保存 fact records，caller 自提 fact
  state 會被阻擋；
- caller 不能在 analysis 內嵌 source body、官方聲明、content hash 或 trust
  decision；
- `not_found_in_scope` 不得升格為「不存在反面見解」。

## 固定信任邊界

所有 analysis 都是 `untrusted_client_proposal`。Validator 只核對：

- schema、分支、scope 與核心 dimensions；
- server-owned source／evidence／fact references；
- source freshness 與 evidence eligibility；
- normative source 的 temporal applicability、authority 與 legal validity；
- determinate assessment 是否具有 server-owned support；
- counter-authority 與 procedural-posture qualifications。

回傳結果固定：

- `validation_scope=structural_and_trust_invariants_only`；
- `semantic_entailment_performed=false`；
- `authorizes_final_answer=false`。

## 不可宣稱能力

v0.7.1 不得被描述為：

- 完整台灣法律資料庫或 production SLA；
- 自動判斷實體法律涵攝正確性的 semantic entailment engine；
- 自動判斷證據能力、證明力或程序爭點正確性的系統；
- 完整刑法三階層、共犯、競合、未遂或量刑引擎；
- 完整行政裁量、比例原則、信賴保護或憲法審查判斷引擎；
- 系統性反面見解搜尋或「不存在反面見解」的證明；
- 完整歷史法規版本服務；
- 取代律師、法院或其他具資格專業人員的個案判斷。
