# ALR-TW Error Codes

## v0.7.0 provider and research codes

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
| `EXTERNAL_RESEARCH_PLAN_REQUIRED` | `client_assisted` run 尚未登錄研究計畫，不執行研究 |
| `CLIENT_ASSISTED_DISCOVERY_NOT_ENABLED` | `server_managed` run 不接受外部計畫登錄 |
| `RESEARCH_PLAN_REGISTRATION_CLOSED` | Run 已開始研究，外部計畫登錄窗口已關閉 |
| `RESEARCH_PLAN_ALREADY_REGISTERED` | Run 已有 immutable registered plan，不接受替換 |
| `RESEARCH_PLAN_REQUIRED_LOCATOR_MISSING` | 外部計畫缺少本 run obligation 所需 material locator |
| `CLIENT_ASSISTED_LAW_LOCATOR_UNRESOLVED` | 外部法規 locator 無法解析成法規名稱＋條號，不改跑關鍵字搜尋 |
| `CLIENT_ASSISTED_JUDGMENT_LOCATOR_MISSING` | 計畫未提供普通裁判 locator，不改跑關鍵字或 TLR 搜尋 |
| `CLIENT_ASSISTED_CONSTITUTIONAL_LOCATOR_UNRESOLVED` | 外部憲法 locator 無法正規化，不改跑關鍵字搜尋 |
| `CLIENT_AUTHORITY_LOCATORS_CANDIDATE_ONLY` | 外部 locator 已登錄為候選，仍須官方 exact lookup |
| `CLAIM_BINDING_ISSUE_NOT_IN_PLAN` | Final claim binding 引用了計畫中不存在的 issue ID |
| `CORE_RESEARCH_ISSUE_UNBOUND` | 至少一個需要結論的 core issue 未綁定 final claim |
| `ANALYSIS_SOURCE_NOT_SERVER_OWNED` | Civil analysis 引用的 source ID 不屬於同一 run |
| `ANALYSIS_EVIDENCE_NOT_SERVER_OWNED` | Civil analysis 引用的 evidence ID 不屬於同一 run |
| `ANALYSIS_FACT_NOT_SERVER_OWNED` | Civil analysis 引用的 fact ID 未由 server context 提供 |
| `ANALYSIS_SOURCE_STALE` | Civil analysis 引用的 source 已過期 |
| `ANALYSIS_SOURCE_NOT_EVIDENCE_ELIGIBLE` | Civil analysis 引用的 source 未取得 evidence 資格 |
| `ANALYSIS_EVIDENCE_NOT_ELIGIBLE` | Civil analysis 引用的 evidence 不可支援分析 |
| `CLAIM_BASIS_SOURCE_REQUIRED` | Civil claim 缺少 normative legal-basis source |
| `MET_ELEMENT_NORMATIVE_SOURCE_REQUIRED` | `met` element 缺少 normative source |
| `MET_ELEMENT_FACT_OR_EVIDENCE_REQUIRED` | `met` element 未綁 fact 或 evidence |
| `MET_ELEMENT_SUPPORT_NOT_ESTABLISHED` | `met` element 綁定的 fact／evidence 未取得 server-owned support |
| `ELEMENT_BURDEN_RECORD_REQUIRED` | Element 缺少逐要件舉證責任紀錄 |
| `BURDEN_NORMATIVE_SOURCE_REQUIRED` | 舉證責任配置缺少 normative source |
| `BURDEN_ALLOCATION_UNRESOLVED` | 舉證責任主體、移轉或證明標準仍有不確定性 |
| `LEGAL_CONTEXT_NOT_VERIFIED` | Normative source 缺少 server-produced legal context |
| `LEGAL_CONTEXT_INCOMPLETE` | Temporal／authority／validity provider coverage 不完整 |
| `LEGAL_TIME_NOT_APPLICABLE` | Normative source 未確認適用於指定法律時點 |
| `LEGAL_VALIDITY_NOT_CONFIRMED` | Normative source 的法律效力未確認 |
| `NORMATIVE_AUTHORITY_NOT_BINDING` | 要件未綁至少一個 binding normative authority |
| `NORMATIVE_AUTHORITY_UNUSABLE` | Normative authority 已被取代或狀態不明 |
| `COUNTER_AUTHORITY_ABSENCE_NOT_ESTABLISHED` | bounded scope 查無結果，不得推論不存在反面見解 |
| `COUNTER_AUTHORITY_COVERAGE_INCOMPLETE` | 未執行、未完成或失敗的反面見解搜尋必須揭露 |
| `PROCEDURAL_POSTURE_UNRESOLVED` | 程序階段尚未確認 |
| `CITATION_OCCURRENCE_EVIDENCE_NOT_BOUND` | Citation occurrence 指向未綁定該 claim 的 evidence |
| `CITATION_OCCURRENCE_TEXT_MISMATCH` | Citation offsets 與 answer 實際文字不一致 |
| `CITATION_OCCURRENCE_SOURCE_MISMATCH` | Citation text 不符合 bound evidence 的 source citation／identifier |
| `CITATION_OCCURRENCE_OUTSIDE_BOUND_CLAUSE` | Citation 與 claim 不在同一 bounded clause |
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
