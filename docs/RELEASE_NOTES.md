# ALR-TW v0.7.0 版本說明

v0.7.0 將 ALR-TW 更新為前端無關、provider-neutral 的台灣法律研究驗證
harness。以下只列本版新增與調整的能力。

## 研究流程與 MCP

- 新增能力協商工具 `get_legal_research_capabilities`；
- 新增研究計畫與法源 locator 契約，支援 `server_managed` 與
  `client_assisted` discovery mode；
- 新增 `submit_legal_research_plan`，外部計畫、locator 與信任判斷維持
  untrusted client proposal；
- 新增 `validate_civil_analysis`，將外部民事法律分析交由 server 驗證；
- `claim_bindings` 支援 issue-level coverage，核心爭點可與最終主張明確關聯；
- 既有 server-owned research tools 維持相容。

## 台灣大陸法系法律分析契約

- 新增 `CivilLawAnalysis` envelope，統一描述 claims、elements、defenses、
  counter-authority 與 procedural posture；
- 新增法律效果分類：`right_constituting`、`right_impeding`、
  `right_extinguishing`、`defense`、`liability_reduction`、
  `remedy_calculation`；
- 新增逐要件舉證責任欄位，涵蓋 burden bearer、presumption、burden shift、
  standard of proof 與 rebuttal status；
- 新增 fact／evidence 狀態：`alleged`、`admitted`、`disputed`、`supported`、
  `proven`、`contradicted`、`inadmissible`、`excluded`；
- 新增 provider-neutral temporal、authority 與 legal-validity context 契約；
- `met` element 必須綁定 server-owned normative source 與 fact 或 eligible
  evidence。

## 官方來源與候選召回

- TLR 維持 clean-room candidate-only adapter；候選仍須回查司法院官方全文，
  不得直接成為正式引用；
- 官方法規、普通裁判與憲法法庭 provider 維持獨立的來源與角色驗證；
- 司法院舊式裁判頁、五段 legacy JID、搜尋 fallback 與現行法日期語意處理
  納入統一研究流程；
- source、evidence、claim、issue、authority 與 legal context 的信任判斷均由
  server 端計算，外部 client 不得自行升格或宣告 final decision。

## 相容性與資料邊界

- `validated`、`qualified`、`blocked` final decision 維持 fail-closed 規則；
- blocked 結果不回傳可呈現的 answer body；
- synthetic、official-only、hybrid-verified 三種資料模式維持；
- provider-neutral contract 允許使用者接入自有法規、裁判與其他合規資料來源；
- 公開套件不內含 LLM、production corpus、私有索引或使用者資料。
