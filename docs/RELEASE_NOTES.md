# ALR-TW v0.7.0

v0.7.0 是台灣法律 Agentic RAG／MCP research safety harness 的
agent-neutral public preview。外部 agent／LLM 負責爭點辨識、構成要件、初步
涵攝與擬稿；ALR-TW 在 server 端管理研究狀態、官方來源、證據升格、法律
結構驗證、引用驗證與答案是否可呈現。

架構採台灣大陸法系角度：法規與法律時點優先，普通裁判依審級及段落角色
處理，憲法法庭多數意見與個別意見分離。ALR-TW 不是法律意見服務，也不以
外部檢索結果取代官方法源。

## v0.7.0 能力

- agent-neutral interoperability：前端先協商能力，再以
  `server_managed` 或 `client_assisted` 建立研究流程；
- `ResearchPlanProposal`、法律爭點與 authority locator 採 provider-neutral
  contract，client 提案永遠是 `untrusted_client_proposal`；
- `CivilLawAnalysis` 公開 envelope，涵蓋 claims、elements、defenses、
  counter-authority、procedural posture、法律效果與 fact/evidence states；
- 逐要件舉證責任紀錄，`met` element 必須綁 server-owned normative source
  以及 fact 或 eligible evidence；
- temporal／authority／legal-validity provider contracts 與 fail-closed
  `validate_civil_analysis`；它是結構／信任驗證，不是 semantic entailment；
- 官方法規、司法院普通裁判與憲法法庭 provider；普通裁判直接解析司法院
  搜尋頁與全文頁，不需要司法院 API token；
- TLR clean-room adapter：在 `hybrid_verified` 提供普通裁判 candidate-only
  recall，所有候選仍須回查司法院官方全文；
- 舊式 `hlExportPDF`、`/EXPORTFILE/ExportToPdf.aspx`、五段 legacy JID、搜尋
  fallback、現行法日期語意與 bounded local reranking；不猜補版本尾碼；
- server-owned research state、短期 SQLite、TTL、ephemeral run、同步 purge、
  deterministic grounding 與 output privacy；
- validated／qualified／blocked final decision，blocked 不回傳 answer body；
- public-boundary lint、synthetic fixtures 與完整契約測試。

## 可選外部服務

- [TLR（Taiwan Legal RAG）](https://github.com/aa0101181514/tw-legal-rag)：
  普通裁判候選召回來源；排序與摘要不能直接作正式引用；
- `mcp-taiwan-legal-db`：僅作行為與介面參考，不是相依套件或整合元件。

## 已知限制

- 不提供 LLM、完整台灣法律資料庫、production corpus、完整歷史法規版本或
  production SLA；
- 不宣稱真正 semantic entailment、複雜涵攝正確性、系統性反面見解搜尋、
  完整審級關係、所有程序裁定、附件／OCR 或特別法自動適用；
- `not_found_in_scope` 不得推論不存在反面見解；
- `hybrid_verified` 會將通過 privacy gate 的查詢送往 TLR；使用者不得輸入
  個人秘密、未公開案情、私有契約、訴訟策略、證據弱點或談判底線；
- 所有輸出仍應由具資格人員依官方原文、法律時點與具體事實複核。

## 工程與安全文件

- 架構與可信邊界：[ARCHITECTURE_CONTRACT.md](ARCHITECTURE_CONTRACT.md)
- MCP tools 與輸入輸出契約：[TOOL_CONTRACT.md](TOOL_CONTRACT.md)
- 前端無關整合契約：[INTEROPERABILITY_CONTRACT.md](INTEROPERABILITY_CONTRACT.md)
- TLR provider 與 candidate-only 規則：[TLR_PROVIDER.md](TLR_PROVIDER.md)
- 官方來源取得方式：[OFFICIAL_PROVIDERS.md](OFFICIAL_PROVIDERS.md)
- 研究資料保存與清除：[STORAGE_AND_PURGE.md](STORAGE_AND_PURGE.md)
- Trust model：[TRUST_MODEL.md](TRUST_MODEL.md)
- Data policy：[../DATA_POLICY.md](../DATA_POLICY.md)
- Release acceptance：[V070_INTEROPERABILITY_ACCEPTANCE.md](V070_INTEROPERABILITY_ACCEPTANCE.md)
- Release audit：[V070_RELEASE_AUDIT.md](V070_RELEASE_AUDIT.md)
- 歷史版本變更：[../CHANGELOG.md](../CHANGELOG.md)

## 發布識別

- release tag：`v0.7.0`
- release title：`v0.7.0`
- current branch：`main`
