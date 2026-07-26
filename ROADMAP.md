# Roadmap

## 已完成

- `v0.1`：synthetic data、source trust policy、citation validation、CI guards。
- `v0.2`：deterministic execution graph、MCP stdio、trace、validation report。
- `v0.3`：claim grounding、role-aware semantic checks、fail-closed scenarios。
- `v0.4`：opt-in identifier-backed judgment cache resolver 與 hash verification。
- `v0.5`：externally driven MCP traces、agent client guide、release hardening。
- `v0.6`：server-owned research service、統一短期 SQLite、官方法規／普通裁判／憲法 provider、clean-room TLR candidate recall、MCP tools、purge 與 public-preview release audit。

## v0.6 公開預覽限制

- 完整指定日期法規版本尚未提供；
- 普通裁判不承諾全域召回率，完整審級圖尚未提供；
- 程序裁定、附件與 OCR 依官方頁面可取得程度處理；
- 普通裁判全文 live lookup 直接使用司法院裁判書查詢與全文頁，不需要 Judicial Yuan API token；
- 沒有內建 LLM、法律答案生成器或 production corpus。

## v0.7 開發方向：Agent-neutral verification runtime

私人 Legal Portal 是上游孵化場與 production/reference implementation；
ALR-TW 是單向、contract-first、public-safe 的獨立萃取，不是平行完整產品，
也不依賴私人 runtime。外部專案負責爭點辨識、構成要件拆解、涵攝與文字
生成；ALR-TW 保持為公開 contracts、validators、研究狀態、官方驗證、
evidence promotion 與 final decision 執行層。

P0／v0.7：

- `get_legal_research_capabilities`：前端先協商能力與信任責任；
- `server_managed`／`client_assisted` discovery modes；
- provider-neutral `ResearchPlanProposal`、法律爭點與 authority locator；
- client locator 永遠 candidate-only，不能注入 evidence 或 trust decision；
- client-assisted locator 直接走官方 exact lookup，避免同輪重複 TLR／關鍵字召回；
- `claim_bindings.issue_ids` 與核心爭點明示覆蓋；
- public `CivilLawAnalysis`：claims、elements、defenses、counter-authority、
  procedural posture 與完整法律效果 taxonomy；
- 逐要件 burden-of-proof，以及 alleged／admitted／disputed／supported／
  proven／contradicted／inadmissible／excluded 狀態；
- provider-neutral temporal／authority／legal-validity contracts、
  fail-closed validator 與 synthetic provider；
- `validate_civil_analysis` MCP tool；analysis 仍是
  `untrusted_client_proposal`，不授權 final answer；
- synthetic validated／qualified／blocked end-to-end fixtures；
- public-boundary lint 禁止私人 runtime dependency、production data、
  operator state、private manifests、ranking calibration 與 gold labels；
- 原有 v0.6 六個高階工具維持向下相容。

## v0.8 候選：Applicability 與 counter-authority

- 特別法／普通法、上位法／下位法、新舊法 applicability resolver；
- 系統化 counter-authority contract 與 appellate／negative-treatment validator；
- 憲法效力、程序要件、救濟與請求權競合模型；
- 公開 provider SDK；production data 仍由使用者自備；
- 完成真實能力與 bounded evaluation 後，才允許 capability 回報支援。

## v0.9 候選：可插拔語義與其他法律領域

- semantic verifier plugin interface，但不得宣稱取代律師判斷；
- 刑事、行政及其他領域 analysis envelopes；
- 律師標註 gold benchmark 與跨領域回歸測試；gold data 不進公開 repo。

## 共同未解限制

- 真正 semantic entailment 與複雜涵攝正確性；
- 系統化反面見解主動探勘與「不存在」證明；
- 完整歷史法規與 amendment lineage；
- 不確定法律概念的形式化判斷；
- 特別法自動適用、請求權競合、法律效果與損害合併；
- 證據能力、證明力、程序時點，以及刑事完整三階層／共犯／競合／未遂；
- 行政、勞動、家事、消保、公司、證券、智財、稅法、採購及執行模板。

詳見 [Agent-neutral interoperability contract](docs/INTEROPERABILITY_CONTRACT.md)
與 [v0.7 development acceptance](docs/V070_INTEROPERABILITY_ACCEPTANCE.md)。

後續功能不得改變 `candidate != evidence`、官方移除要同步治理、角色不可混用與 blocked 不洩漏草稿等核心 invariant。
