# Changelog

## 0.9.1 - 2026-08-14

### Security

- Legacy `answer_with_validation()` 現將 raw citation mappings 一律視為
  caller-controlled，且移除 caller 自行宣告的 `identifier_resolution`；僅靠
  `source_tier=official`、URL、hash 或偽造的 `hash_match` 不再能取得
  `final_eligible` 或 `safe_to_present=true`。
- Legacy metadata validation 不再將 `support=not_checked` 誤標為
  `claim_support_level=source_verified`。法律答案呈現仍須使用 server-owned
  `ResearchService.validate_legal_answer`。

### Changed

- `SyntheticOfficialAdapter` 保留相容名稱，但其 manifest 與 records 改為
  `synthetic`／`demo_only`；legacy agentic demo 現會 fail closed，且不回傳可呈現
  answer body。
- 新增 caller-attested official URL、偽造 resolver 狀態、legacy trust gate 與
  synthetic demo-only 的回歸測試；公開 MCP 的 caller-attestation 拒絕行為維持不變。

## 0.9.0 - 2026-08-14

### Added

- 裁判語境 attribution 與 disposition contracts：區分本院、原審、當事人及其他
  發話者，並將上訴駁回、維持、廢棄發回、撤銷改判、部分准許與程序駁回分開保存；
  無法唯一解析時維持 fail-closed。
- `HistoricalLawQuery`、`HistoricalLawResolution` 與
  `LegislativeHistoryProviderAdapter`：提供立法院／官方歷史法規 provider 的
  bounded port，法條版本與立法資料分離，並要求明示法律時點及 server-owned
  source／snapshot binding。
- 既有 public-law SDK、applicability resolver 與 finalization gate 的銜接契約；
  公開套件不附 endpoint、credentials、corpus 或 production deployment state。
- `alr-tw.semantic-verifier-request/v1`、`alr-tw.semantic-verifier-result/v1` 與
  `alr-tw.semantic-verifier-validation/v1`：提供 optional、advisory-only 的
  semantic verifier plugin 邊界；plugin 不能建立 evidence、改變 source trust
  或授權 finalization／答案。
- 六個 `LegalAnalysisEnvelope` 分支的 additive domain fields：五個
  issue-oriented 分支可表達 issue-level burden、defenses、branch procedural
  posture 與 refusal constraints；民法分支保留 element-level schema，所有引用
  仍由 server-owned validator 重新檢查。

- provider conformance 與 receipt-aware adapter：統一檢查 official／candidate-only
  provider 的 source、evidence、scope、retry、privacy 與 snapshot receipt binding；
  沒有 server-owned receipt 時不得升格 ordinary。
- optional semantic sidecar registration 與 deployer provider boundary contract：
  sidecar 維持 shadow／advisory-only，部署者自備 corpus 與模型不進入公開套件，
  且不得成為 evidence、trust 或 final-decision owner。
- 新增公開發布用 repository-scoped secret-scan policy，將 synthetic redaction
  fixture 的例外範圍限制在單一測試檔案。

以下版本段落是歷史變更紀錄，不代表目前 v0.9.1 的能力或公開宣稱。

## 0.8.0 - 2026-08-08

### Added

- 新增研究充分性與 Coverage v2：區分流程完成、研究充分性及答案模式，並保存 bounded scope、provider scope、原因碼與 snapshot receipt 參照。
- 新增 server-owned `get_legal_research_finalization` 與 structured refusal 契約，統一由伺服器決定 ordinary、conditional 或 refusal-only 姿態。
- 新增 bounded counter-authority candidate discovery 與官方驗證契約；未分類反方關係不得升格為全球不存在或實務一致。
- 新增 provider-neutral applicability resolver，支援由 server-owned metadata
  表達特別法／普通法、上位法／下位法與新舊法時點關係；解析與驗證要求獨立的
  server-owned source catalog binding，無法唯一確認時 fail closed。
- 新增 authority／judgment-lineage contracts，保存法院層級、程序姿態、上訴／
  審查鏈與 bounded negative-treatment 結果，且不執行 semantic opposition classification。
- 新增行政規則、行政解釋、訴願與立法資料的 public-law contracts，以及可替換的
  provider SDK／adapter 介面；資料由部署者自備，candidate 與 evidence 仍分離。

### Changed

- `ready_for_draft` 現僅表示 workflow completion；最終答案須同時通過 research sufficiency 與 finalization gate。
- 新增 provider-neutral snapshot consistency 與 absence-claim gate；synthetic fixture 僅供 demo／契約測試。
- 既有研究工具與 payload 維持 additive 相容；舊紀錄回讀後由伺服器重新計算充分性。
- provider-neutral snapshot receipt 是公開契約；內建 runtime 尚未簽發或持久化 live-provider receipt，服務輸出最多為 `conditional`／`qualified`，`ordinary` 保留給 receipt-aware adapter。

本專案遵循語意化版本精神；`0.x` 仍屬公開預覽，介面可能調整。

## 0.7.1 - 2026-07-27

### Added

- `alr-tw.legal-analysis/v1` 與 `LegalAnalysisEnvelope`；
- 民法、民事程序、刑法、刑事程序、行政法與憲法審查六種可併用分支；
- 行政法分支內的合法性與救濟 discriminated tracks；
- profile-specific issue taxonomy、`complete`／`issue_limited` scope 與核心
  dimension coverage；
- `validate_legal_analysis` MCP tool；
- interoperability capabilities 的跨領域 schema、tool 與 supported profiles。

### Safety

- 跨領域 analysis 固定為 `untrusted_client_proposal`；
- 所有 normative source、fact 與 evidence ID 必須由同一 research run 的
  server-owned context 確認；
- 確定的 `met`／`not_met` 結論若無 server-owned support 會 fail closed；
- `issue_limited`、未解決議題與 counter-authority 缺口會明示 qualification；
- analysis validation 不執行 semantic entailment，也不授權 final answer。

### Changed

- 法律分析統一為 `alr-tw.legal-analysis/v1` 與
  `validate_legal_analysis`；移除預覽期的平行民法信封與獨立驗證工具。

## 0.7.0 - 2026-07-26

### Added

- agent-neutral interoperability capabilities contract；
- `get_legal_research_capabilities` 與 `submit_legal_research_plan` MCP tools；
- `server_managed`／`client_assisted` discovery ownership；
- provider-neutral legal issue、authority locator 與 immutable registered-plan contracts；
- `claim_bindings.issue_ids` 與 explicit core-issue coverage；
- 結構化民法 claims、elements、六種法律效果、逐要件舉證責任、defenses、
  fact/evidence states、counter-authority 與 procedural posture；
- provider-neutral temporal／authority／legal-validity contracts 與
  synthetic-only context provider；
- 結構化 analysis 的 validated／qualified／blocked synthetic end-to-end
  fixtures；
- public-boundary lint 對未公開 runtime dependency、production state、
  calibration 與 gold-label artifacts 的阻擋。

### Safety

- external research plans are always `untrusted_client_proposal`；
- caller authority locators remain candidate-only and cannot include evidence or trust decisions；
- client-assisted runs fail before research when the required plan or locator type is missing；
- registered judgment locators use official exact lookup and do not trigger a duplicate keyword/TLR recall pass；
- issue binding coverage is explicitly reported as non-entailment；
- civil analysis、fact/evidence status 與 authority locator 一律保留
  `untrusted_client_proposal` 邊界；
- `met` element 必須綁 server-owned normative source 以及 fact 或 eligible
  evidence；
- `not_found_in_scope` 不得表示不存在反面見解；
- 公開 package 不依賴未公開部署、production corpus、索引、manifest 或
  operational state。

### Release status

- v0.7.0 is a public-preview, agent-neutral verification runtime；它不是完整
  台灣法律資料庫、semantic entailment engine 或 production SLA；
- TLR 僅作 ordinary-judgment candidate recall，正式證據仍須由 ALR-TW 回查
  司法院官方全文；
- temporal／authority／legal-validity provider contract 已公開，但內建
  synthetic provider 不宣稱 production legal correctness；
- release acceptance、synthetic end-to-end、325 tests、Ruff、mypy、公開邊界、
  forbidden-file、diff 與 fresh-wheel smoke 均已執行。

## 0.6.2 - 2026-07-22

### Fixed

- 支援舊式 `hlExportPDF?type=JD&id=...` 與實際 `/EXPORTFILE/ExportToPdf.aspx?type=JD&id=...` 識別標記，仍要求頁面識別碼與請求值完全一致；
- TLR 五段 doc ID 不再直接淘汰；系統會以原值查詢官方頁面，優先採用頁面唯一提供的六段 canonical JID；若舊頁本身只明示相同五段 ID，則保留為 `legacy_five_part_jid`，絕不猜補版本序號；
- 司法院搜尋可處理 POST 直接回傳結果清單，以及只有結果連結、沒有 iframe 的頁面變體；
- `as_of_date` 等於查詢當日時視為現行法問題，不再誤標 `HISTORICAL_LAW_VERSION_UNSUPPORTED`；
- TLR 候選在官方回查前加入有長度上限的本地文字相關性與民刑事衝突降權，降低明顯無關候選占用五筆驗證額度。

### Safety

- TLR 排序只影響候選驗證順序，不會讓外部摘要直接取得 evidence 資格；
- 舊頁相容修正沒有移除 identifier mismatch 的 fail-closed 閘門；六段請求若只能取得五段標記，會以明確的 legacy ambiguity error 阻擋；
- 自然語言法規議題規劃、系統性反方裁判搜尋與研究充分性狀態重整仍保留至 v0.7.0。

## 0.6.1 - 2026-07-22

### Fixed

- MCP `tools/call` 在嚴格業務參數驗證前相容 `params._meta` 與 direct `arguments._meta`，其他未知欄位仍拒絕；
- 普通裁判 parser 改為 recursive block extraction 與 role-safe state machine；section 不完整時保留 `partial` official source，不再整份 fatal drop；
- `PARTY_ARGUMENT`、`MIXED`、`UNKNOWN` 預設不可支援法院見解；
- TLR `doc_id`／官方 URL 改用 typed candidate identity，排序去重後回司法院 exact lookup，JID mismatch 會阻擋升格；
- outbound query privacy 與 answer output privacy 分離，答案不再受 180 字外送門檻影響；
- 法規、憲法 keyword-only 與未執行的 counter-authority search 不再被標成 substantive coverage complete。

### Added

- `deterministic_grounding_v2`：NFKC、中文 2–4 gram、polarity、qualifier、role 與 legal/numeric anchor guards；
- `validate_legal_answer.claim_bindings`，以 evidence ID 綁定核心主張；
- answer validation v3 的 `privacy`、`binding_mode`、`verification_method`、`semantic_entailment_performed` 與 `coverage_summary`；
- TLR candidate resolution provenance 與 verification budget metrics。

### Behavior changes

- 只有 `answer_text`、沒有 explicit binding 的舊 caller 仍可呼叫，但會標示 `legacy_unbound`；核心法律主張不再允許以 run-wide 最高字面重疊進入 `validated`；
- 公開版未執行系統性反方裁判搜尋時，答案至多以明確 coverage qualification 呈現；
- `JUDGMENT_PARSE_PARTIAL`、candidate resolve failure 或 verification truncation 會保留 source，但使 ordinary-judgment recall 標示不完整。

### Release status

- 程式、synthetic contract gates、fresh-wheel host canary 與 live provider canaries 已通過；v0.6.1 依 [V0.6.1 Release Audit](docs/V061_RELEASE_AUDIT.md) 以已揭露的 ordinary-court real-corpus 驗證限制發布。該限制不視為 gate 通過。

## 0.6.0 - 2026-07-19

### Added

- server-owned research run、obligation state machine、idempotent operations；
- 統一 SQLite storage、TTL、run/all purge 與 ephemeral retention；
- 六個 MCP tools：建立、繼續、讀取、精確來源查詢、答案驗證、清除；
- 法務部中央法規、司法院普通裁判、憲法法庭官方 providers；
- JID 與正式裁判字號的官方精確解析；
- clean-room TLR candidate-only provider 與本地 privacy gate；
- official live snapshot evidence promotion、expiry 與 claim-support validation；
- `alr-tw doctor`、`alr-tw purge` 與 live-mode 設定。

### Changed

- package 與 MCP server version 升至 `0.6.0`；
- MCP protocol negotiation 支援 `2025-11-25`、`2025-06-18`、`2025-03-26` 與 `2024-11-05`；
- blocked final validation 不再回傳 answer body；
- 普通裁判與憲法裁判意見角色採大陸法系資料分類，不把當事人主張或個別意見當成法院多數理由。

### Security

- caller-supplied `official`／`verified_cache` metadata 不再能自我證明 final eligibility；
- 只有 server-resolved official snapshot 或 resolver-backed hash match 可進入正式證據層；
- 外部查詢、redirect、response size、schema、secret redaction 與 source expiry 採 fail-closed。

### Limitations

- 公開預覽，不提供法律意見或完整法律資料庫；
- 指定歷史日期的完整法規版本、普通裁判全域召回率與完整審級關係尚未承諾；
- 普通裁判全文 live lookup 改為直接解析司法院裁判書查詢與全文頁，不需要司法院 API token。
