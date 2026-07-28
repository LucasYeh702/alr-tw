# Roadmap

## Current release: v0.7.1

v0.7.1 是 agent-neutral、provider-neutral 的台灣法律研究驗證 runtime。
ALR-TW 是獨立的、contract-first、public-safe 公開法律研究驗證 harness，
不綁定特定 agent、資料 provider 或部署環境。

目前公開能力：

- `get_legal_research_capabilities`：先協商 provider、模式與信任責任；
- `server_managed`／`client_assisted` discovery modes；
- provider-neutral `ResearchPlanProposal`、法律爭點與 authority locator；
- client locator 永遠是 candidate-only，不能注入 evidence 或 trust decision；
- client-assisted locator 直接走官方 exact lookup，避免同輪重複 TLR／關鍵字召回；
- TLR clean-room adapter 可在 `hybrid_verified` 提供普通裁判候選召回，仍須回查司法院官方全文；
- `claim_bindings.issue_ids` 與核心爭點明示覆蓋；
- public `LegalAnalysisEnvelope`：以單一 `analyses` 清單承載民法、
  民事程序、刑法、刑事程序、行政法與憲法審查六個可併用分支；
- 民法分支保留 claims、elements、defenses 與完整法律效果 taxonomy；
- 逐要件 burden-of-proof，以及 alleged／admitted／disputed／supported／
  proven／contradicted／inadmissible／excluded 狀態；
- provider-neutral temporal／authority／legal-validity contracts、fail-closed
  validator 與 synthetic provider；
- 單一 `validate_legal_analysis` MCP tool；analysis 永遠是
  `untrusted_client_proposal`，不授權 final answer；
- 行政法分支內以 `legality`／`remedy` tracks 表達合法性與救濟；
- 每個分支明列核心 dimensions、`complete`／`issue_limited`
  scope、normative source、fact／evidence references 及 fail-closed 結果；
- 官方法規、司法院裁判與憲法法庭 provider，含舊式裁判頁、五段 legacy JID、
  搜尋 fallback 與現行法日期語意處理；
- synthetic validated／qualified／blocked end-to-end fixtures；
- public-boundary lint 禁止未公開 runtime dependency、production data、operator
  state、private manifests、ranking calibration 與 gold labels。

## 已知限制

- 不提供 LLM、法律答案生成器或完整台灣法律資料庫；
- 不承諾完整歷史法規版本、普通裁判全域召回率、完整審級關係、所有程序裁定、
  附件或 OCR；
- 不提供真正 semantic entailment、複雜涵攝正確性或系統性反面見解搜尋；
- 不自動完成特別法優先、請求權競合、法律效果與損害合併；
- 六種可併用分支只驗證結構、scope 與 server-owned references；
  不會判斷證據能力、證明力、刑法三階層或行政裁量等實體涵攝是否正確；
- 勞動、家事、消保、公司、證券、智財、稅法、採購及強制執行等專門
  profiles 尚未提供；
- `hybrid_verified` 會將通過 privacy gate 的查詢送往 TLR；TLR 只作候選召回，
  正式證據仍須由 ALR-TW 回查官方來源。

## 後續方向

### v0.8 候選：Applicability 與 counter-authority

- 特別法／普通法、上位法／下位法、新舊法 applicability resolver；
- 系統化 counter-authority contract 與 appellate／negative-treatment validator；
- 憲法效力、程序要件、救濟與請求權競合模型；
- 公開 provider SDK；production data 仍由使用者自備；
- 完成真實能力與 bounded evaluation 後，才允許 capability 回報支援。

### v0.9 候選：可插拔語義與專門法律領域

- semantic verifier plugin interface，但不得宣稱取代律師判斷；
- 勞動、家事、消保、公司、證券、智財、稅法、採購及強制執行等專門
  analysis profiles；
- 律師標註 gold benchmark 與跨領域回歸測試；gold data 不進公開 repo。

歷史版本與已完成工作的逐版紀錄請見 [CHANGELOG.md](CHANGELOG.md)。

詳見 [Agent-neutral interoperability contract](docs/INTEROPERABILITY_CONTRACT.md)
與 [v0.7.1 domain analysis acceptance](docs/V071_DOMAIN_ANALYSIS_ACCEPTANCE.md)。

後續功能不得改變 `candidate != evidence`、官方移除要同步治理、角色不可混用
與 blocked 不洩漏草稿等核心 invariant。
