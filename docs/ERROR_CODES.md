# ALR-TW Error Codes

## v0.9.0 contract codes

| Code | Meaning |
|---|---|
| `JUDGMENT_SEMANTICS_RUN_MISMATCH` | 裁判語境結果與 server research run 不一致 |
| `JUDGMENT_SEMANTICS_SOURCE_NOT_SERVER_BOUND` | 裁判語境 source 不在 server-owned source scope |
| `JUDGMENT_SEMANTICS_TRUST_STATUS_FORGED` | Caller 嘗試偽造 parser trust status |
| `JUDGMENT_SEMANTICS_SEMANTIC_FLAG_FORGED` | Caller 嘗試偽造 semantic entailment 狀態 |
| `JUDGMENT_ATTRIBUTION_SOURCE_NOT_BOUND` | Attribution section 引用未綁定 source |
| `JUDGMENT_ATTRIBUTION_EVIDENCE_NOT_BOUND` | Attribution section 引用未綁定 evidence |
| `JUDGMENT_ATTRIBUTION_ELIGIBILITY_FORGED` | 非本院／未解析 attribution 嘗試自我宣告可支援主張 |
| `JUDGMENT_DISPOSITION_UNRESOLVED` | 主文未能唯一分類，不能把理由推導為裁判結果 |
| `JUDGMENT_CURRENT_COURT_ATTRIBUTION_UNRESOLVED` | 本院發話者或其與主文關係未能唯一確認 |
| `HISTORICAL_LAW_IDENTIFIER_OR_NAME_REQUIRED` | 歷史法規查詢缺少法規識別碼或名稱 |
| `HISTORICAL_LAW_BOUNDED_SCOPE_REQUIRED` | 歷史法規查詢缺少 bounded provider scope |
| `HISTORICAL_LAW_PROVIDER_MISMATCH` | 歷史法規 resolution 與 provider 不一致 |
| `HISTORICAL_LAW_SOURCE_ROLE_OVERLAP` | 法條版本與立法資料 source ID 重疊 |
| `HISTORICAL_LAW_SOURCE_NOT_IN_RESULT` | Resolution 引用 provider result 未返回的 source |
| `HISTORICAL_LAW_NORMATIVE_SOURCE_MISSING` | 只有立法資料，沒有可供 applicability 的法條版本 |
| `HISTORICAL_LAW_NORMATIVE_SOURCE_NOT_SERVER_OWNED` | 法條版本 source 未綁定 server catalog |
| `HISTORICAL_LAW_NORMATIVE_ROLE_MISMATCH` | 法條版本 source role 不是 normative text |
| `HISTORICAL_LAW_SOURCE_ROLE_INVALID` | Provider 回傳的法條／立法資料分類無法安全驗證 |

## v0.9.0 provider and research codes

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
| `ANALYSIS_SOURCE_NOT_SERVER_OWNED` | Analysis 引用的 source ID 不屬於同一 run |
| `ANALYSIS_EVIDENCE_NOT_SERVER_OWNED` | Analysis 引用的 evidence ID 不屬於同一 run |
| `ANALYSIS_FACT_NOT_SERVER_OWNED` | Analysis 引用的 fact ID 未由 server context 提供 |
| `ANALYSIS_SOURCE_STALE` | Analysis 引用的 source 已過期 |
| `ANALYSIS_SOURCE_NOT_EVIDENCE_ELIGIBLE` | Analysis 引用的 source 未取得 evidence 資格 |
| `ANALYSIS_EVIDENCE_NOT_ELIGIBLE` | Analysis 引用的 evidence 不可支援分析 |
| `DOMAIN_ANALYSIS_SCOPE_LIMITED` | 分支只涵蓋選定 issues，不得宣稱完整分析 |
| `DOMAIN_PROFILE_CORE_DIMENSION_MISSING` | `complete` 分支缺少必要核心 dimension |
| `DOMAIN_ISSUE_NORMATIVE_SOURCE_REQUIRED` | 領域 issue 缺少 normative source |
| `DOMAIN_ISSUE_UNRESOLVED` | 領域 issue 仍為 `uncertain`，必須揭露 |
| `CIVIL_CLAIM_LEGAL_BASIS_REQUIRED` | 民法 claim 缺少 normative legal-basis source |
| `DETERMINATE_ELEMENT_NORMATIVE_SOURCE_REQUIRED` | 確定的民法 element 缺少 normative source |
| `DETERMINATE_DEFENSE_NORMATIVE_SOURCE_REQUIRED` | 確定的民法 defense 缺少 normative source |
| `DETERMINATE_ANALYSIS_FACT_OR_EVIDENCE_REQUIRED` | `met`／`not_met` 判斷未綁定 fact 或 evidence |
| `DETERMINATE_ANALYSIS_SUPPORT_NOT_ESTABLISHED` | 確定判斷的 fact／evidence 未取得 server-owned support |
| `CIVIL_ELEMENT_UNRESOLVED` | 民法 element 仍為 `uncertain`，必須揭露 |
| `CIVIL_DEFENSE_UNRESOLVED` | 民法 defense 仍為 `uncertain`，必須揭露 |
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

## v0.9.0 applicability and authority-lineage codes

| Code | Meaning |
|---|---|
| `APPLICABILITY_SOURCE_NOT_FOUND` | Server catalog 缺少請求的 normative source |
| `APPLICABILITY_SOURCE_NOT_SERVER_OWNED` | Applicability source 不是 server-owned record |
| `APPLICABILITY_SOURCE_NOT_VERIFIED` | Source 尚未取得官方／evidence-eligible trust status |
| `APPLICABILITY_SERVER_CATALOG_INCOMPLETE` | 來源關係無法在 bounded server catalog 內核對 |
| `APPLICABILITY_SERVER_CATALOG_BINDING_REQUIRED` | Applicability resolver 缺少獨立 server-owned source catalog binding |
| `APPLICABILITY_SERVER_CATALOG_BINDING_INVALID` | Server source catalog binding 含重複或非法 source ID |
| `APPLICABILITY_SOURCE_NOT_SERVER_BOUND` | Requested source ID 不在獨立 server-owned catalog binding |
| `APPLICABILITY_SOURCE_NOT_YET_EFFECTIVE` | Source 的 effective-from 晚於指定法律時點 |
| `APPLICABILITY_SOURCE_EXPIRED_OR_REPEALED` | Source 在指定法律時點已失效或廢止 |
| `APPLICABILITY_HISTORICAL_VERSION_UNAVAILABLE` | 指定時點缺少可核對的適用版本 |
| `APPLICABILITY_NO_ACTIVE_SOURCE` | Bounded source set 在指定時點沒有 active source |
| `APPLICABILITY_SCOPE_MISMATCH` | Source scope 與 request scope 不一致 |
| `APPLICABILITY_RELATION_TARGET_NOT_IN_SCOPE` | 明示的特別／上位／新舊關係目標不在請求範圍 |
| `APPLICABILITY_RELATION_UNRESOLVED` | 多個 active source 缺少可核對的優先關係 |
| `APPLICABILITY_ACTIVE_SOURCES_CONFLICT` | 明示關係仍留下多個互相衝突的 active source |
| `APPLICABILITY_RELATION_CYCLE` | Applicability relation graph 含循環 |
| `APPLICABILITY_SERVER_RESOLUTION_MISMATCH` | Caller resolution 與 server deterministic recomputation 不一致 |
| `AUTHORITY_LINEAGE_FOREIGN_SOURCE_ID` | Lineage 引用不屬於同一 server run 的 source |
| `AUTHORITY_LINEAGE_FOREIGN_EVIDENCE_ID` | Lineage 引用不屬於同一 server run 的 evidence |
| `AUTHORITY_LINEAGE_RUN_MISMATCH` | Lineage contract 與 server run 不一致 |
| `AUTHORITY_LINEAGE_SOURCE_NOT_SERVER_OWNED` | Lineage node 不是 server-owned source |
| `AUTHORITY_LINEAGE_POSTURE_SOURCE_UNBOUND` | Procedure posture 未綁定 node source |
| `AUTHORITY_LINEAGE_COVERAGE_INCOMPLETE` | Lineage provider coverage 不是 complete |
| `AUTHORITY_LINEAGE_NOT_FOUND_IS_BOUNDED_ONLY` | `not_found_in_scope` 僅限 bounded scope，不支持全球不存在主張 |
| `NEGATIVE_TREATMENT_SEMANTIC_CLASSIFICATION_NOT_PERFORMED` | Provider treatment 尚未經 semantic opposition classifier |

## v0.9.0 public-law provider and SDK codes

| Code | Meaning |
|---|---|
| `PUBLIC_LAW_RESULT_SCHEMA_INVALID` | Public-law provider result 不符合公開 schema |
| `PUBLIC_LAW_SERVER_METADATA_BINDING_REQUIRED` | Result 缺少 server-issued metadata binding |
| `PUBLIC_LAW_SERVER_METADATA_MISMATCH` | Result metadata 與 server snapshot 不一致 |
| `PUBLIC_LAW_SERVER_METADATA_NOT_CURRENT` | Snapshot metadata 已過期或尚未生效 |
| `PUBLIC_LAW_PROVIDER_NOT_AVAILABLE` | Provider 回報 blocked／retry-required，禁止升格 |
| `PUBLIC_LAW_COVERAGE_PARTIAL` | Public-law provider 結果只有 bounded partial coverage |
| `PUBLIC_LAW_CANDIDATES_ONLY` | 結果只有 candidate，尚未成為 evidence |
| `PUBLIC_LAW_NOT_FOUND_IN_BOUNDED_SCOPE` | Bounded scope 查無資料，不表示全球不存在 |
| `PUBLIC_LAW_BACKEND_STATUS_UNSUPPORTED` | Backend 回傳不支援的狀態 |
| `PUBLIC_LAW_BACKEND_PROVIDER_MISMATCH` | Backend provider ID 與 adapter 不一致 |
| `PUBLIC_LAW_BACKEND_QUERY_MISMATCH` | Backend query ID 與 request 不一致 |
| `PUBLIC_LAW_BACKEND_TRUNCATION_CONFLICT` | Backend 同時宣稱 truncated 與 complete |
| `PUBLIC_LAW_RESULT_LIMIT_TRUNCATED` | Adapter 依 max-results 限制截斷結果 |
| `PUBLIC_LAW_SERVER_METADATA_ISSUER_REQUIRED` | 缺少 server metadata issuer，不能聲稱 scoped absence |
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
| `RESEARCH_COVERAGE_QUALIFIED` | 研究有必要官方證據但存在 bounded coverage 限制，答案只能 conditional |
| `REQUIRED_COVERAGE_MISSING` | 必要法規、官方驗證或明示時點 coverage 缺失，必須 refusal |
| `REQUIRED_COVERAGE_INCOMPLETE` | 必要 provider／官方驗證暫時不完整，需 retry 或 refusal |
| `SOFT_COVERAGE_MISSING` | counter-authority 等非核心 coverage 缺失，只能 qualified/conditional |
| `RESEARCH_SUFFICIENCY_RETRY_REQUIRED` | 暫時性 provider error／timeout 使研究不得定稿 |
| `WORKFLOW_INCOMPLETE` | 研究 obligation 尚未完成；`ready_for_draft` 仍未取得 |
| `RESEARCH_INSUFFICIENT` | 研究完成但必要法源、證據或 Coverage gate 不足，只能拒答 |
| `RESEARCH_RETRY_REQUIRED` | server-owned obligation 或 coverage 有可重試的暫時性缺口 |
| `RESEARCH_REQUIRED_OBLIGATION_PENDING` | 必要 obligation 保留 pending，等待新的 operation_id 重試 |
| `RESEARCH_REQUIRED_OBLIGATION_BLOCKED` | 必要 obligation 被永久政策、隱私或不支援條件阻擋 |
| `NO_SERVER_VERIFIED_EVIDENCE` | run 沒有可供答案層使用的 server-owned evidence |
| `SERVER_EVIDENCE_REQUIRED` | finalization／validation 需要 server-owned source/evidence references |
| `SERVER_EVIDENCE_UNAVAILABLE` | 宣稱可用的 server evidence 無法由 run store 取得 |
| `SERVER_EVIDENCE_STALE_OR_INELIGIBLE` | evidence 過期、信任層級或 claim-support eligibility 不符 |
| `ORDINARY_GATE_NOT_SATISFIED` | 尚未同時滿足 sufficient、完整必要 coverage、snapshot 與 evidence gate |
| `ANSWER_RESEARCH_STATE_NOT_READY` | 未到可驗證流程階段即提交答案；必須先完成 research/finalization |
| `ABSENCE_CLAIM_NOT_ESTABLISHED` | bounded counter-authority scope 不足以主張不存在反面見解 |
| `ABSENCE_CLAIM_SCOPE_MISSING` | absence claim 缺少 query/time/provider scope 或 successful provider receipt |
| `SNAPSHOT_RECEIPT_SET_MISMATCH` | run 所需 provider snapshot set 與 server receipt 不一致 |
| `SNAPSHOT_RECEIPT_NOT_SERVER_OWNED` | snapshot receipt 不是由 server-owned provider/result 產生 |
| `SNAPSHOT_RECEIPT_SERVER_BINDING_REQUIRED` | finalization 缺少 server-owned snapshot binding |
| `SNAPSHOT_GENERATION_MISMATCH` | provider snapshot generation 與 run receipt 不一致 |
| `FINALIZATION_SOURCE_NOT_SERVER_OWNED` | finalization 引用的 source 不屬於 server-owned run |
| `FINALIZATION_EVIDENCE_NOT_SERVER_OWNED` | finalization 引用的 evidence 不屬於 server-owned run |
| `SNAPSHOT_RECEIPT_MISMATCH` | provider snapshot receipt 與 run scope 或世代不一致 |
| `SNAPSHOT_RECEIPT_MISSING_LEGACY` | 舊紀錄沒有 receipt；不得據此宣稱 ordinary sufficiency |
| `ANSWER_REFUSAL_ONLY` | finalization 只允許結構化拒答，不回傳草稿 |

## v0.9.0 semantic-verifier plugin codes

| Code | Meaning |
|---|---|
| `SEMANTIC_VERIFIER_REQUEST_NOT_SERVER_OWNED` | plugin request 不是由 server-owned research run 發出 |
| `SEMANTIC_VERIFIER_REQUEST_TARGET_NOT_SERVER_OWNED` | request target 不在獨立 server target set |
| `SEMANTIC_VERIFIER_REQUEST_TARGET_INVALID` | request target schema 無法驗證 |
| `SEMANTIC_VERIFIER_SERVER_TARGET_INVALID` | server target binding schema 無法驗證 |
| `SEMANTIC_VERIFIER_TARGET_NOT_SERVER_OWNED` | plugin finding 指向未知或外部 target |
| `SEMANTIC_VERIFIER_RUN_NOT_SERVER_BOUND` | plugin request/result 與 server run 不一致 |
| `SEMANTIC_VERIFIER_REQUEST_ID_MISMATCH` | plugin result 不屬於該 verifier request |
| `SEMANTIC_VERIFIER_PLUGIN_ID_MISMATCH` | plugin result 身分與註冊 adapter 不一致 |
| `SEMANTIC_VERIFIER_PLUGIN_VERSION_MISMATCH` | plugin result 版本與註冊 adapter 不一致 |
| `SEMANTIC_VERIFIER_PLUGIN_ID_MISSING` | plugin 未提供穩定的 plugin ID |
| `SEMANTIC_VERIFIER_PLUGIN_VERSION_MISSING` | plugin 未提供穩定的 plugin version |
| `SEMANTIC_VERIFIER_PLUGIN_EXECUTION_FAILED` | plugin 執行失敗；不得降級為 clean miss |
| `SEMANTIC_VERIFIER_RUN_FAILED` | plugin 明示執行失敗；結果必須 blocked |
| `SEMANTIC_VERIFIER_RESULT_INVALID` | plugin result schema 無法驗證 |
| `SEMANTIC_VERIFIER_FINDING_INVALID` | 個別 plugin finding 無法驗證 |
| `SEMANTIC_VERIFIER_FINDINGS_INVALID` | plugin findings 不是 bounded sequence |
| `SEMANTIC_VERIFIER_SUPPORT_REFERENCE_REQUIRED` | supports／contradicts 必須引用 server-owned source 或 evidence |
| `SEMANTIC_VERIFIER_SOURCE_NOT_SERVER_OWNED` | finding 引用不屬於該 run 的 source |
| `SEMANTIC_VERIFIER_EVIDENCE_NOT_SERVER_OWNED` | finding 引用不屬於該 run 的 evidence |
| `SEMANTIC_VERIFIER_SOURCE_NOT_ELIGIBLE` | source 過期或不是 evidence eligible |
| `SEMANTIC_VERIFIER_EVIDENCE_NOT_ELIGIBLE` | evidence 過期、foreign 或不具 claim-support eligibility |
| `SEMANTIC_VERIFIER_SOURCE_OUTSIDE_TARGET_SCOPE` | finding 引用 target 未宣告的 source |
| `SEMANTIC_VERIFIER_EVIDENCE_OUTSIDE_TARGET_SCOPE` | finding 引用 target 未宣告的 evidence |
| `SEMANTIC_VERIFIER_AUTHORITY_SENTINEL_FORGED` | plugin 試圖授權 evidence、trust、finalization 或答案 |
| `SEMANTIC_VERIFIER_EVALUATION_SENTINEL_INVALID` | semantic evaluation sentinel 不合法 |
| `SEMANTIC_VERIFIER_TARGET_DUPLICATED` | plugin 對同一 target 回傳多筆 finding |
| `SEMANTIC_VERIFIER_TARGET_COVERAGE_PARTIAL` | completed plugin 結果未涵蓋所有 requested targets |

## v0.9.0 provider conformance and boundary codes

| Code | Meaning |
|---|---|
| PROVIDER_RESULT_SCHEMA_INVALID | Common provider result 無法驗證 |
| PROVIDER_ID_MISMATCH | Provider result 與 server request 身分不一致 |
| PROVIDER_SOURCE_ID_DUPLICATE | Provider source reference 重複 |
| PROVIDER_EVIDENCE_ID_DUPLICATE | Provider evidence reference 重複 |
| PROVIDER_SERVER_SOURCE_BINDING_REQUIRED | Source promotion 缺少獨立 server source catalog binding |
| PROVIDER_SERVER_EVIDENCE_BINDING_REQUIRED | Evidence promotion 缺少獨立 server evidence catalog binding |
| PROVIDER_SOURCE_NOT_SERVER_BOUND | Source ID 不在 server-owned catalog／object scope |
| PROVIDER_EVIDENCE_NOT_SERVER_BOUND | Evidence ID 不在 server-owned catalog／object scope |
| PROVIDER_SOURCE_NOT_EVIDENCE_ELIGIBLE | Source trust status 不允許 evidence promotion |
| PROVIDER_SOURCE_STALE | Source 已過期 |
| PROVIDER_SOURCE_TIMESTAMP_FUTURE | Source fetched／verified timestamp 尚未到達 server decision time |
| PROVIDER_SERVER_SOURCE_BINDING_INVALID | Server source catalog binding 含重複 ID |
| PROVIDER_SERVER_EVIDENCE_BINDING_INVALID | Server evidence catalog binding 含重複 ID |
| PROVIDER_EVIDENCE_SOURCE_NOT_ELIGIBLE | Evidence 未綁定可引用 source |
| PROVIDER_CANDIDATE_PROMOTION_FORBIDDEN | Candidate-only provider 嘗試提交 source／evidence |
| PROVIDER_ERROR_RETRY_REQUIRED | Provider error 不得被解讀為 clean miss |
| PROVIDER_BOUNDED_SCOPE_REQUIRED | NOT_FOUND 缺少 bounded scope，不能建立 absence claim |
| PROVIDER_SNAPSHOT_RECEIPT_REQUIRED | Conformance profile 明示需要 server receipt |
| PROVIDER_SNAPSHOT_NOT_CONSISTENT | Receipt 與 server run set 不一致或非當前 |
| PROVIDER_SNAPSHOT_RECEIPT_MISSING | Source／evidence 有效但尚無 receipt，只能 qualified |
| PROVIDER_METADATA_SENSITIVE_FIELD | Provider metadata 含疑似 credential／secret 欄位 |
| PROVIDER_METADATA_PRIVATE_DEPLOYMENT_MARKER | Provider metadata 含私有部署路徑或連線 marker |
| SIDECAR_EVIDENCE_CREATION_FORBIDDEN | Sidecar 不得建立 evidence |
| SIDECAR_SOURCE_TRUST_MUTATION_FORBIDDEN | Sidecar 不得改變 source trust |
| SIDECAR_FINALIZATION_AUTHORIZATION_FORBIDDEN | Sidecar 不得授權 finalization |
| SIDECAR_PRESENTABLE_ANSWER_FORBIDDEN | Sidecar 不得輸出可呈現答案 |
| SIDECAR_BUNDLED_MODEL_FORBIDDEN | 公開套件不得 bundled model |
| SIDECAR_BUNDLED_CORPUS_FORBIDDEN | 公開套件不得 bundled corpus |
| DEPLOYER_BUNDLED_CORPUS_FORBIDDEN | Deployer declaration 不得宣告公開套件含 corpus |
| DEPLOYER_PRIVATE_DATA_FORBIDDEN | 公開套件不得含 private data |
| DEPLOYER_CREDENTIALS_FORBIDDEN | 公開套件不得含 credentials |
| DEPLOYER_DEPLOYMENT_PARAMETERS_FORBIDDEN | 公開套件不得含 deployment parameters |

## v0.9.0 legal-analysis domain constraint codes

| Code | Meaning |
|---|---|
| `DOMAIN_BURDEN_NOT_DECLARED` | issue-oriented branch 未宣告 issue-level burden（info） |
| `DOMAIN_DEFENSES_NOT_DECLARED` | issue-oriented branch 未宣告 defenses／exceptions（info） |
| `DOMAIN_BURDEN_NORMATIVE_SOURCE_REQUIRED` | domain burden 缺少 server-owned normative source |
| `DOMAIN_BURDEN_ALLOCATION_UNRESOLVED` | burden bearer、shift 或 standard 尚未釐清 |
| `DOMAIN_DEFENSE_NORMATIVE_SOURCE_REQUIRED` | domain defense 缺少 normative source |
| `DOMAIN_DEFENSE_UNRESOLVED` | domain defense 的狀態仍 unresolved |
| `DOMAIN_PROCEDURAL_POSTURE_NOT_DECLARED` | branch 未宣告 branch-specific procedural posture（info） |
| `DOMAIN_PROCEDURAL_POSTURE_UNRESOLVED` | branch procedural posture 尚未釐清 |
| `DOMAIN_REFUSAL_CONSTRAINT_NOT_DECLARED` | unresolved domain condition 未宣告對應拒答條件 |

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
