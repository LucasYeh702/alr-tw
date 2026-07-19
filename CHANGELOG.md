# Changelog

本專案遵循語意化版本精神；`0.x` 仍屬公開預覽，介面可能調整。

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
