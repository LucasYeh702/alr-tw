# Public / Private Boundary

ALR-TW is a sanitized public reference harness. It does not ship production legal
data, local indexes, caches, logs, credentials, or private workflow data.

| Category | Public repo |
|---|---|
| Source policy | yes |
| Citation validator | yes |
| Trust gate | yes |
| Synthetic fixtures | yes |
| Trace schema | yes |
| Production corpus | no |
| SQLite shards | no |
| Chroma DB | no |
| Verified cache | schema only |
| Logs | no |
| Private workflow data | no |

The full local runtime can replace the synthetic adapters with compliant legal
data sources. The public repo keeps only the schemas, policies, deterministic
harness, tests, examples, and documentation needed to review the trust boundary.

