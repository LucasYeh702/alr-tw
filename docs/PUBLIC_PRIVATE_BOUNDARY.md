# Public / Private Boundary

## v0.10.0 public boundary

ALR-TW is an independent, public-safe provider-neutral harness. The public
package contains provider contracts, stateless validators, deterministic trust
rules, synthetic fixtures, and boundary tests only. It has no dependency on
non-public deployment paths, corpora, indexes, manifests, or operational state.

公開 repo 現在包含真實官方端點的有界 provider code 與 clean-room TLR adapter，但不包含下載後的 production corpus、永久 cache、token 或真實查詢。Live provider 在 operator 明確選擇模式後才執行；`synthetic` 仍是唯一 implicit default。

Provider code 可公開，不代表 provider 回應、使用者 run database 或 query logs 可公開。`~/.cache/alr-tw`、自訂 `ALR_TW_STORAGE_PATH`、`.env`、shell history、debug capture 與 MCP client logs 都在 repo 邊界外，發布前必須另外稽核。

其他法律資料庫／MCP 專案只能作公開介面與行為參考；不得複製其非授權程式碼、私有資料或 trust claims。本 repo 的 authority 決定必須由自己的 contracts、providers 與 tests 證明。

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
