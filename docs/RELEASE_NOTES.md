# ALR-TW v0.7.1 版本說明

v0.7.1 統一台灣大陸法系的結構化法律分析接口。

## 統一法律分析

- 新增單一 `alr-tw.legal-analysis/v1` 的 `LegalAnalysisEnvelope`；
- `analyses` 可同時承載六個不可重複的分析分支：
  - `civil_substantive`（民法）；
  - `civil_procedure`（民事程序）；
  - `criminal_substantive`（刑法）；
  - `criminal_procedure`（刑事程序）；
  - `administrative`（行政法）；
  - `constitutional_review`（憲法審查）；
- 行政法分支內以 `legality`／`remedy` 分軌表達合法性與救濟；
- 民法分支提供 claims、elements、defenses、逐要件舉證責任與法律效果
  分類；
- 各分支支援 `complete` 與 `issue_limited` 範圍，並檢查核心面向；
- 確定的 `met`／`not_met` 判斷必須綁定由伺服器管理的 fact 或可採用的
  evidence，規範判斷必須綁定 normative source。

## MCP 與能力協商

- 使用單一 `validate_legal_analysis` MCP tool；
- `get_legal_research_capabilities` 回傳統一 schema、tool 名稱及六個
  supported profiles；
- 移除預覽期的平行民法信封與獨立民法驗證工具。

## 安全邊界

- 分析提案固定為 `untrusted_client_proposal`；
- source、evidence、fact、法律時點、authority 與 validity 仍由
  伺服器管理的研究內容核定；
- 受管理的 `ResearchService` 不接受呼叫端自我認證的 fact state；
- `issue_limited`、未解決議題與反向權威資料涵蓋不足會明示
  限制；
- 分析驗證固定
  `authorizes_final_answer=false`、`semantic_entailment_performed=false`。
