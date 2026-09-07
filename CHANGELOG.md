# Changelog

## 0.12.0 - 2026-09-05

### Added

- Prompt-selectable bounded quick research (`/quick`、`快速模式：`) with a
  maximum-five official judgment verification budget.
- `execute_legal_research` and `ResearchService.execute_run_to_completion()` for
  bounded single-roundtrip server-owned orchestration, elapsed-time telemetry,
  and a verified evidence bundle at the drafting boundary.
- Provider-neutral candidate/lineage protocols and a read-only
  `alr-tw verify-provider --input` conformance-envelope command.
- A version-pinned, gold-free ChronoLex-TW evaluation adapter whose historical
  version metric requires evaluator-owned server adjudication.
- A non-answer `research_brief` projection for verified source locators,
  obligation progress, blockers, and safe next actions.

### Changed

- A non-empty officially verified judgment subset may now reach the existing
  `qualified` / `conditional` posture when remaining candidate checks are
  bounded, rejected, or budget-truncated. Zero verified sources, stale or
  foreign evidence, and claim-binding failures remain fail closed.
- Quick judgment lookup omits unrequested breadth such as counter-authority and
  lineage expansion, while retaining explicit statutory lookup, privacy
  screening, exact source verification, evidence sufficiency, and final answer
  validation.
- Official HTTPS transports use the operating-system certificate store through
  `truststore`; TLR HTTPS uses the same backend. `doctor --live` performs
  bounded official-provider probes.

### Fixed

- Official-law memory snapshots retain their original fetched, verified and
  expiry times. Expiry or forced refresh revokes old data before reloading;
  failures and lookups cannot revive or extend stale material. I/O crossing
  expiry returns no eligible source or evidence.
- Release CI exercises isolated base/TLR-only wheel installs, including
  Python 3.11 and 3.12, while retaining built-distribution boundary scans.

- Large passage sets no longer overflow the 512-ID finalization field: the
  field is a deterministic preview and the full server-owned set is digest-bound.
- Unusable external candidates now trigger official fallback; malformed
  candidate privacy receipts and provider/source/evidence mismatches fail closed.
- Counter-authority uses deterministic queries of at most 128 characters, TLR
  judgment and public-law responses cannot exceed requested top-K, and
  two-character statute names are retained for exact lookup.
- `include_counter_authority=true` with `research_depth=quick` now fail-closes
  instead of silently omitting counter-authority.
- Package, installed metadata, and MCP `serverInfo` share the `0.12.0` identity.
- Evidence bundles reserve bounded capacity for statutes and constitutional
  materials instead of allowing five judgment sources to displace them.
- `verify-provider` rejects JSON `null` collections with structured output
  instead of an uncaught exception.
- Caller-supplied provider envelopes receive structural checks only; the CLI
  cannot certify live origin, issue trusted receipts, or authorize presentation.
- Bare JIDs and formal judgment citations route to official verification in
  quick mode. `execute_legal_research.operation_prefix` labels steps only and
  does not promise request idempotency.
- Public-boundary checks also reject private review governance and review
  directories; regression scenarios use synthetic, non-personal inputs.
- The standalone `tlr` extra declares `truststore`, matching its HTTPS transport
  dependency rather than relying on the separate `live` extra being installed.
- Built sdist checks use the package root so wrapper directories cannot hide
  forbidden data paths; out-of-package tar members are rejected. The installed
  boundary checker also rejects private-key/data suffixes and local markers.
- TLS diagnostics recognize certificate errors in wrapped exceptions without
  misclassifying a timeout merely because its message contains `ssl`.

### Compatibility

- Existing step-by-step tools and the v0.11 `ProviderSet(tlr=...)` constructor
  slot remain available. New integrations should use `candidate_recall` and
  `lineage_candidates`.

## 0.11.0 - 2026-09-03

### Added

- TLR provider 新增行政函釋／稅務函釋語意候選召回，投影為
  `PublicLawCandidate`；不建立 source、server metadata 或 evidence，效力狀態與
  查無結果都維持外部 provider 的 bounded metadata。
- TLR 普通裁判候選新增 `hit_excerpt` 投影與有界長全文分頁；回傳每頁 offset、
  全文總字數、截斷狀態及續讀 offset。完整讀取 TLR 文本仍固定
  `evidence_eligible=false`，正式 evidence 只由 ALR-TW 官方驗證產生。
- 新增 server-owned `inspect_judgment_lineage`：以 TLR `/v1/fulltext` 的
  `case_history.upper/lower` 作 bounded 歷審候選，再由目前設定的官方裁判
  provider 逐筆回查正文並分類上訴駁回、維持、廢棄發回或廢棄改判。
- 歷審結果綁定既有 `AuthorityLineageContract`；只有 TLR 的廢棄標記與官方
  上級審主文分類同時成立時，才回報 confirmed reversal。查無上級審不推論
  裁判確定，也不宣稱已完成前後審見解的語義比較。
- 新增可選的唯讀本機裁判 provider；搜尋結果維持 candidate-only，精確查詢會檢查
  catalog-bound receipt、coverage binding、來源狀態與 trusted-text／provenance
  hash。candidate-only 快取不會升格；未符合本機快取條件時以 JID／正式字號回查
  官方來源。

### Changed

- 資料層說明改為可選接入：部署者可使用 TLR，或由前端呼叫相容法律資料
  服務，再以 `client_assisted` 提交候選 locator；正式 evidence 仍由 ALR-TW 驗證。
- 統一套件、MCP 與現行文件的版本標示，補齊本機裁判 provider 的共用介面型別。

## 0.10.1 - 2026-08-26

### Fixed

- 將「是否找到已驗證反面裁判」與「搜尋涵蓋是否完整」拆成獨立狀態；
  已驗證的 `opposing` relation receipt 現可完成 counter-authority obligation，
  即使查證預算截斷仍保留 `coverage=partial`。
- 外部 reasoning owner 可對同一 run 的已驗證裁判提出 `supporting`、
  `opposing`、`distinguishing`、`unrelated` 或 `uncertain` 關係分析；ALR-TW
  會驗證 source、evidence、資格、期限與 hash 後保存不可變 receipt。
- `unrelated` 裁判不再被誤判為反面裁判；不存在、過期、不合格或跨來源的
  evidence 會 fail closed，且不產生 relation receipt。
- Finalization 現分別消費 counter-authority obligation 狀態與 bounded coverage，
  不再因「找到任何已驗證裁判」本身固定降為 partial／refusal-only；全國一致或
  不存在反面見解的主張仍要求完整且有界的搜尋涵蓋。

## 0.10.0 - 2026-08-20

### Added

- 新增單一 MCP tool catalog 與 `verified`、`compatibility`、`demo` 三種
  tool profile；capabilities 會回報 session 實際 profile 與可用工具名稱。
- 新增 server-owned `lookup_legislative_history` 與 optional、唯讀且有界限的
  立法院開放資料 connector，將議案提案、法律條文對照表、委員會議案、
  黨團協商及三讀議案建模為 typed、candidate-only legislative locators。
- 新增 Agent 工具選型指南與可複製的 agent-neutral `templates/AGENTS.md`。

### Changed

- `official_only` 與 `hybrid_verified` 預設只列出 server-owned tools；
  `synthetic` 預設保留完整 demo surface。需要舊工具的部署可明示設定
  `ALR_TW_MCP_TOOL_PROFILE=compatibility` 或 `demo`。
- Synthetic fixture tools 與 legacy compatibility tools 在 description 首行
  分別標示 `[DEMO ONLY]` 與 `[LEGACY COMPATIBILITY]`，並導向對應的
  server-owned tools。

### Security

- MCP `tools/list` 與 `tools/call` 共用同一個 session-fixed profile gate；
  隱藏工具的直接或快取呼叫固定回
  `TOOL_NOT_AVAILABLE_IN_PROFILE`，未知 profile 在啟動時 fail closed。
- 立法院 connector 不接受 caller 任意 URL，限制 HTTPS official hosts、
  redirect、timeout、payload size、JSON shape、結果數及查詢範圍。
- `data.ly.gov.tw` 目前需要 legacy-server-connect TLS 相容；connector 僅對固定
  官方 origin 使用該 client-side 初始連線旗標，仍保留 CA／hostname 驗證並
  禁止連線建立後重新協商。
- 立法資料維持 candidate-only；linked PDF／DOC 不在本版解析，也不能取代
  正式公布法規、server-owned evidence promotion 或答案驗證。

### Known limitations

- 立法院資料集的屆期、欄位與文件日期覆蓋不一致；缺少可驗證時點、正式公布
  版本或唯一議案關聯時，結果維持 partial／qualified，不能由 scoped miss
  推論不存在立法理由或沿革。
- 本版不提供關係文書 PDF／DOC 解析、完整歷史法規版本庫或 production SLA。

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

以下版本段落是歷史變更紀錄，不代表目前 v0.12.0 的能力或公開宣稱。

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
- 內建 `ResearchService` 現會依同一 run 的官方／可信快取 source 與 evidence
  集合簽發、持久化 provider-neutral snapshot receipt；finalization 從 server-owned
  store 重算 binding。receipt 完整且其他閘門通過時 `ordinary` 可達，缺失最高為
  `conditional`，過期、跨 run 或材料不一致則 fail closed。
- 新增集中式 v0.12 公開紅隊與 verified-profile 通過／拒絕雙路徑測試；量測公開
  正向 fixtures 的 false-refuse count，並保留「閘門通過但法律結論仍可能錯」為
  RESULTS 限制，而不是虛構成測試失敗。

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
- TLR candidate-only provider 與本地 privacy gate；
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
