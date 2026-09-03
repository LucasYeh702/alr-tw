# Public / Private Boundary

## v0.11.0 public boundary

ALR-TW is an independent, public-safe provider-neutral harness. The public
package contains provider contracts, stateless validators, deterministic trust
rules, synthetic fixtures, and boundary tests only. It has no dependency on
non-public deployment paths, corpora, indexes, manifests, or operational state.

公開 repo 包含官方來源查詢、可選的 TLR 候選召回與唯讀本機裁判 provider 介面；資料集、下載內容、永久 cache、token 與真實查詢由部署端管理，不隨套件發布。Live provider 在 operator 明確選擇模式後才執行；`synthetic` 仍是唯一 implicit default。

Provider code 可公開，不代表 provider 回應、使用者 run database 或 query logs 可公開。`~/.cache/alr-tw`、自訂 `ALR_TW_STORAGE_PATH`、`.env`、shell history、debug capture 與 MCP client logs 都在 repo 邊界外，發布前必須另外稽核。

部署者可選用相容的法律資料庫／MCP 服務，並依其授權接入候選或 locator。
前端取得的外部結果可透過 `client_assisted` 提交；來源資格、證據綁定與正式
答案授權仍由 ALR-TW 的 server-owned 驗證流程決定。

ALR-TW is a sanitized public reference harness. It does not ship production legal
data, local indexes, caches, logs, credentials, or private workflow data.

| Category | Public repo |
|---|---|
| Source policy | yes |
| Citation validator | yes |
| Trust gate | yes |
| Synthetic fixtures | yes |
| Trace schema | yes |
| Unified `LegalAnalysisEnvelope` and stateless validator | yes |
| Temporal / authority / validity provider contract | yes |
| Research sufficiency, Coverage v2, finalization and snapshot receipt contracts | yes |
| Production corpus | no |
| SQLite shards | no |
| Chroma DB | no |
| Verified cache | schema only |
| Logs | no |
| Private workflow data | no |
| Production catalogs, registries, manifests, and reconciliation state | no |
| Schedulers, operator attestations, backup, rollback, and release state | no |
| Private gold labels and ranking calibration | no |

A user-owned runtime can replace the synthetic adapters with compliant legal
data sources through provider-neutral contracts. The public repo keeps only the
schemas, policies, deterministic harness, tests, examples, and documentation
needed to review the trust boundary.
