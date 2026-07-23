# ALR-TW Error Codes

## v0.6 provider and research codes

| Code | Meaning |
|---|---|
| `CONFIG_MODE_REQUIRED` | Live command 未明確選擇 `official_only`／`hybrid_verified` |
| `INVALID_IDENTIFIER` | JID、正式裁判字號或憲法字號無法正規化 |
| `AMBIGUOUS_FORMAL_CITATION` | 正式裁判字號對應多個官方 JID，需補民／刑事等類別 |
| `OFFICIAL_SESSION_REQUIRED` | 某個可選官方來源需要 operator session；普通裁判網站主路徑不使用此碼 |
| `OFFICIAL_SOURCE_UNAVAILABLE` | 官方網路或服務不可用；不是 not found |
| `OFFICIAL_SOURCE_NOT_FOUND` | 官方完成精確查詢後不存在或已移除 |
| `OFFICIAL_SCHEMA_CHANGED` | 官方結構與受支援 schema 不符 |
| `OFFICIAL_PARSE_ERROR` | 回應存在但無法安全解析 |
| `OFFICIAL_CONTENT_CONFLICT` | 官方結構化資料與官方頁面內容衝突 |
| `LEGACY_JUDGMENT_IDENTIFIER_UNRESOLVED` | 五段式舊判決查詢頁未提供可核對的官方識別標記；不得猜測版本尾碼 |
| `LEGACY_JUDGMENT_IDENTIFIER_AMBIGUOUS` | 六段式請求只取得五段式官方標記，無法唯一驗證版本尾碼 |
| `TLR_UNAVAILABLE` | TLR timeout、HTTP 或 schema failure |
| `SEMANTIC_RECALL_DEGRADED` | 外部召回失敗，effective mode 已降為 official-only |
| `PRIVACY_EXTERNAL_QUERY_BLOCKED` | 查詢為 sensitive／uncertain，禁止送外部 |
| `CALLER_ATTESTED_SOURCE` | Caller metadata 不能自我證明 final eligibility |
| `RESEARCH_RUN_EXPIRED` | Run TTL 已到期 |
| `RESEARCH_OBLIGATION_PENDING` | 尚未完成研究義務即要求 final validation |
| `RESEARCH_RUN_NOT_FOUND` | Run 不存在、已過期清除或已 purge |
| `HISTORICAL_LAW_VERSION_UNSUPPORTED` | 無法以本版資料可靠回答指定歷史時點 |
| `ANSWER_CONTAINS_SENSITIVE_DATA` | Draft 含隱私規則判定的敏感資料 |
| `SOURCE_STALE` | Source snapshot 已過期，不可作 final evidence |
| `SOURCE_REVALIDATION_FAILED` | 過期來源的官方重新驗證失敗 |
| `SOURCE_NOT_EVIDENCE_ELIGIBLE` | 查得來源仍只具候選或不可引用身分 |
| `JUDGMENT_RECALL_INCOMPLETE` | 普通法院召回不完整 |
| `PURGE_CONFIRMATION_REQUIRED` | 清除操作未收到明確確認 |
| `PURGE_PARTIAL_FAILURE` | DB sidecar 或 temp artifact 未完整清除 |
| `ANSWER_QUALIFIED` | 只能連同不可省略的限制文字展示 |
| `ANSWER_BLOCKED` | 草稿不得展示，answer body 已移除 |

Provider `ERROR`、`NOT_FOUND` 與 degraded／partial 必須分開。外部 outage 不得改寫成不存在；candidate-only 不得改寫成 evidence。

| Code | Meaning | Recommended action |
|---|---|---|
| `NO_FINAL_CITATION` | No source qualified as final citation | refuse |
| `REJECTED_CITATION` | Citation source tier or metadata was rejected by trust policy | refuse |
| `UNVERIFIABLE_CITATION` | Citation could not be verified for final use | refuse |
| `LAWS_COVERAGE_LOW` | Required law coverage is absent or low confidence | refuse |
| `JUDGMENTS_COVERAGE_LOW` | Required judgment coverage is absent or low confidence | refuse |
| `CANDIDATE_ONLY_SOURCE` | Source is only a candidate lead | refuse or verify elsewhere |
| `SYNTHETIC_DEMO_ONLY` | Synthetic fixture cannot be legal authority | refuse |
| `VERIFIED_CACHE_INCOMPLETE` | Verified cache metadata is incomplete | refuse |
| `IDENTIFIER_BACKED_DISABLED` | Identifier-backed verified cache is opt-in and not enabled | refuse |
| `IDENTIFIER_MATERIAL_NOT_ELIGIBLE` | Identifier substitution is limited to judgment records | refuse |
| `IDENTIFIER_UNRESOLVED` | Official identifier did not resolve to a local original record | refuse |
| `IDENTIFIER_HASH_MISMATCH` | Recomputed hash of the resolved original record does not match | refuse |
| `COVERAGE_LOW_CONFIDENCE` | Required legal coverage is low | refuse |
| `SOURCE_REJECTED` | Source tier or metadata rejected | refuse |
| `SOURCE_UNVERIFIABLE` | Source could not be verified | refuse |
| `CLAIM_SUPPORT_NOT_CHECKED` | Source exists but claim support was not checked | human_review_required |
| `CLAIM_SUPPORT_UNCHECKED` | Claim-support not evaluated against legal evidence segments | human_review_required |
| `CLAIM_SUPPORT_NEEDS_REVIEW` | Claim support is ambiguous and needs human review | human_review_required |
| `CLAIM_UNSUPPORTED` | One or more core claims have no supporting evidence | refuse |
| `CLAIM_OVERSTATED` | Claim support is broader than provided legal segments | refuse or human_review_required |
| `CLAIM_CONTRADICTED` | Evidence conflicts with the claim text | refuse |
| `CLAIM_ROLE_ERROR` | Claim incorrectly inferred from wrong legal segment role | refuse or human_review_required |
| `HUMAN_REVIEW_REQUIRED` | Human legal review is required | human_review_required |
| `PRIVATE_DATA_NOT_ALLOWED` | Private data must not enter public harness | refuse |
| `PRODUCTION_DATA_EXCLUDED` | Production data is outside public repo | refuse |
| `SCHEMA_VALIDATION_FAILED` | Input or trace schema invalid | refuse |
