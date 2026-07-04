# ALR-TW Threat Model

| Threat | Mitigation |
|---|---|
| Prompt injection | Retrieved content never overrides source/citation policy |
| Tool poisoning | JSON-RPC input validation and source-tier gates |
| Synthetic misuse | `synthetic` is demo-only and cannot become final |
| External recall misuse | `external_semantic_recall` is candidate-only |
| Private data leakage | Production/private data excluded; public boundary checker |
| Verified cache poisoning | this repo checks verified-cache field presence for URL or eligible identifier, hash, and verification time; byte-level re-verification is the deployer's promotion pipeline responsibility, as described in `docs/ARCHITECTURE_CONTRACT.md` |
| Stale source | validation metadata remains explicit |
| Overclaiming | claim support taxonomy and human review state |
