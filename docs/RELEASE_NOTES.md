# ALR-TW v0.6.0 Public Preview

v0.6.0 把 ALR-TW 從 synthetic trust harness 推進為可安裝、可在明確模式下查詢真實官方來源的 agentic legal research harness。

主要新增：

- server-owned research run、ordered obligations 與 idempotent operations；
- 短期 SQLite source/evidence storage、TTL、ephemeral 與 purge；
- 法務部中央法規、司法院普通裁判、憲法法庭 providers；
- TLR clean-room candidate-only recall 與 privacy downgrade；
- 六個 MCP tools 與多版本 protocol negotiation；
- official evidence promotion、freshness、role-aware claim validation；
- caller-attested official metadata fail-closed 修正。

公開預覽限制：完整歷史法規、普通裁判全域召回率、完整審級關係與所有附件／程序裁定仍未承諾。普通裁判直接查詢司法院網站，不需要司法院 API token。

發布前 checklist 見 [RELEASE_AUDIT_PROCEDURE.md](RELEASE_AUDIT_PROCEDURE.md)，本次實際結果見 [V060_RELEASE_AUDIT.md](V060_RELEASE_AUDIT.md)。詳細變更見 [CHANGELOG.md](../CHANGELOG.md)。
