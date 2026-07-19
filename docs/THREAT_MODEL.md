# ALR-TW Threat Model

## Assets

- 使用者查詢、草稿與研究狀態；
- 官方 source snapshots、evidence spans 與 removal status；
- TLR API key、司法院搜尋詞與 operator configuration；
- final decision、citation lineage 與 public-release integrity。

## Primary threats and controls

| Threat | Control |
|---|---|
| Caller 偽造 official metadata | server-owned provider/resolver；caller-attested sources reject |
| TLR candidate 被直接引用 | fixed candidate-only tier；無 evidence id；官方回查 |
| 敏感個案送到外部 | local privacy gate；uncertain 降級 official-only |
| SSRF／惡意 redirect | HTTPS host allowlist、credential/redirect validation |
| 巨大／惡意回應 | timeout、byte cap、ZIP path/file/schema guards |
| 官方 outage 被判 not found | typed provider errors and coverage flags |
| 已移除裁判持續散布 | `removal_required`、managed purge、short TTL |
| 當事人／個別意見冒充法院見解 | section roles and claim-role validation |
| 過期 evidence 支持答案 | `expires_at` check before final validation |
| Blocked 草稿外洩 | answer body set to null before response |
| Secret 寫入 trace/storage | `SecretStr`, redacted doctor, request-time injection |
| Purge 不完整 | shared `PurgeService`, WAL/SHM/temp cleanup tests |

## Residual risks

規則式 privacy gate 不是完整 DLP；外部 provider 可保存日誌；官方 HTML/API 可能變動；即時查詢不等於完整 corpus；filesystem／backup 可能保留刪除痕跡；deterministic 法律角色與 claim checks 不能取代律師複核。

Legacy verified-cache helpers may check field presence, but field presence is not byte verification. A production promotion pipeline must resolve the official original and recompute bytes/hash as defined in [ARCHITECTURE_CONTRACT.md](ARCHITECTURE_CONTRACT.md); the v0.6 MCP boundary instead accepts only server-owned provider/resolver results.
