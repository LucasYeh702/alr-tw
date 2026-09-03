# Roadmap

## Current release: v0.11.0

v0.11.0 是 agent-neutral、provider-neutral 的台灣法律研究驗證 harness，已完成
研究充分性、Coverage v2、finalization、歷史法規、裁判語境安全與可插拔 sidecar
契約。它不是完整台灣
法律資料庫，也不提供法律意見或 production SLA；真實資料 provider 由部署者
依公開契約自行接入。

目前 v0.11.0 已具備的核心能力：

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
- legacy raw citation mappings 固定為 caller-controlled；metadata-only helper
  不再授權答案呈現，synthetic records 固定為 demo-only。

Provider-neutral snapshot receipt 目前只是公開契約與一致性檢查介面。內建
`ResearchService` 尚未簽發或持久化 live-provider receipt，因此服務輸出最多為
`conditional`／`qualified`；`ordinary` 保留給 receipt-aware provider adapter
完成同一 run 的 server-owned receipt binding 後使用。

## v0.11.0：有界歷審檢查與可選資料層

- `inspect_judgment_lineage` 使用 TLR 記錄的上下級審候選，再由 ALR-TW
  回查官方正文並分類主文結果；不推論裁判確定，也不自動比較前後審見解。
- TLR provider 可召回行政／稅務函釋候選，並分頁讀取普通裁判長全文，保留
  命中片段、全文總長、截斷狀態與續讀位置；外部結果不直接成為 evidence。
- 可選唯讀本機裁判 provider 與既有官方 provider 共用查詢介面；前端也可
  使用相容資料服務，再透過 `client_assisted` 提交候選 locator。

後續仍需分別驗收歷審關係涵蓋率、前後審見解比較及官方行政函釋 connector；
本版不把候選資料、主文分類或契約介面宣稱為上述能力已完整完成。

## v0.10.1：官方立法 locator 與 Agent 工具面收斂

v0.10.1 完成兩個分離驗收的 lane：加入有界限的立法院官方資料 locator
connector，以及降低 MCP client 誤選 synthetic／legacy 工具的 Agent
Experience（AX）防呆。兩者都維持既有 server-owned trust boundary；本版仍不作
完整立法沿革、文件解析或 production-ready 承諾。

### Lane A：MCP 工具分類、導流與模式收斂

v0.9.1 的 `tools/list` 在 `synthetic`、`official_only` 與 `hybrid_verified`
三種 data mode 都回傳同一組 24 個工具：10 個 server-owned research tools 與
14 個 legacy／compatibility tools。14 個工具並非全部都是寫死的 mock；其中
包含 synthetic fixture lookup、legacy trace flow、policy introspection 與 claim helpers，
不應未分類就一律以 demo 命名或移除。

已實作：

- 建立單一、可測試的 tool catalog，將工具明確分為 `server_owned`、
  `legacy_compatibility` 與 `synthetic_demo`；`tools/list`、`tools/call`、文件與
  capabilities 使用同一分類，不維護多套可漂移的清單。
- synthetic fixture 工具的 description 首行加上穩定的
  `[DEMO ONLY]` 標記、不可用於真實案件的說明，並指向
  `lookup_legal_source`、`research_legal_question` 或其他對應的
  server-owned 工具；legacy flow 另以 `[LEGACY COMPATIBILITY]` 標示。
- 新增與 data mode 分離、且由 session 啟動時一次解析的 MCP tool
  profile，包含 `verified`、`compatibility` 與 `demo`：
  `official_only`／`hybrid_verified` 預設為 `verified`，`synthetic` 預設為
  `demo`，未知 profile 在啟動時 fail closed。
- 未列於當前 profile 的工具不只從 `tools/list` 隱藏；直接或快取後的
  `tools/call` 也應回傳穩定的 `TOOL_NOT_AVAILABLE_IN_PROFILE` 與建議
  替代工具，不得形成只管 discovery、不管 invocation 的假邊界。
- 保留明示 opt-in 的 migration profile，但不宣稱這是零破壞性變更。
  live mode 的預設 `tools/list` 會改變，應在 changelog、client guide 與
  release notes 說明升級方式。

文件與 AX 驗收：

- 在 README 與 `docs/AGENT_CLIENT_GUIDE.md` 新增 Agent 工具選型矩陣，
  分開單一法源查證、多步驟研究、分析結構驗證、答案驗證與
  demo／CI 情境，並列出每個選擇的 trust effect。
- 提供 optional、agent-neutral 的 `templates/AGENTS.md`，但不宣稱某一
  IDE／模型為唯一支援目標，也不全面禁止外部 discovery。外部搜尋結果
  只能作 candidate，正式引用仍必須回到 server-owned 官方驗證鏈。
- 建立工具選擇回歸 fixtures，至少覆蓋「查某法第 X 條」、「查正式裁判」、
  「進行完整爭點研究」與「執行 synthetic demo」。驗收可證明工具面
  與錯誤路由為 deterministic，但不宣稱任意 LLM 的工具選擇正確率
  可達 100%。

### Lane B：立法院官方立法資料 locator connector

本版已實作：

- 在既有 `LegislativeHistoryBackend` 與 `LegislativeHistoryProviderAdapter`
  契約上實作 optional、唯讀的官方 connector，不把 endpoint、credential、
  全量 corpus 或 deployment state 寫入公開 contract。
- 以立法院開放資料 ID20、ID19、ID46、ID8 與 ID48 的 targeted JSON API
  建立結構化 locator；linked PDF／DOC 不在本版下載或解析。
- 查詢需明示 `as_of_date`、法規識別碼或名稱與 bounded scope。Typed roles
  分開 `proposal_document`、`article_comparison`、`committee_bill`、
  `caucus_record` 與 `third_reading_record`；只有未來實際解析相應正文時才可
  使用 `proposal_reason`、`committee_report` 或 `third_reading_text`。
- 不接受 caller 提供的任意 URL。Connector 檢查 HTTPS official host allowlist、
  redirect、content type、回應大小與 JSON schema；locator 一律先當 candidate，
  本版 connector 本身不簽發 evidence 或正式公布版本。
- 議案文件、條文對照、委員會議案、黨團協商與三讀紀錄不得互相代替。只有
  立法資料而沒有可綁定的正式公布法版本時，結果維持
  `qualified`，不得宣稱該理由就是最終有效條文的單一「立法者意旨」。
- 立法院開放資料的屆期範圍與較早期沿革查詢要分開報告；API timeout、
  文書缺漏、無法建立唯一關聯或官方來源衝突時 fail closed，不用
  `not_found` 推論「沒有立法理由」。

本版驗收：

- 合成 contract tests 覆蓋多提案併案、不同階段理由衝突、缺少最終公布版本、
  惡意／跨網域 URL、redirect、過大或異常 payload、timeout 與較早沿革缺口。
- optional live smoke 分開報告各 dataset 的 HTTP／schema 可用性與 candidate
  數；外部服務 timeout 或空集合不作為離線 CI 的通過條件，也不改寫成完整
  `not_found`。
- README、tool contract 與資料來源顯名同步，並將「功能已實作」、
  「live 已驗證」與「production ready」分開陳述。

後續版本再評估官方關係文書 PDF／DOC 解析、hash／snapshot binding、正式公布
版本關聯、較早期立法沿革與多議案併案圖；完成前不得把 locator 宣稱為已取得的
立法理由正文。

### v0.10.1 共同非目標

- 不宣稱內建 provider 已覆蓋所有台灣法規、裁判、立法沿革或 OCR；
- 不把 tool description、AGENTS 範本或模型選擇測試當成 runtime trust gate；
- 不以立法資料取代現行有效法條、正式公布版本或答案層級的
  claim／citation validation。

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
