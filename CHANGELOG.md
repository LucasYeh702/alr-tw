# Changelog

本專案遵循語意化版本精神；`0.x` 仍屬公開預覽，介面可能調整。

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
