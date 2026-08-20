# ALR-TW Tool Contract

## v0.9.1 interoperability tools

| Tool | Required input | Contract |
|---|---|---|
| `get_legal_research_capabilities` | none | 回傳 agent-neutral ownership、discovery modes、可驗證材料與限制 |
| `submit_legal_research_plan` | `run_id`, `operation_id`, `plan` | 登錄 immutable untrusted issue／locator proposal；不能產生 evidence |
| `validate_legal_analysis` | `run_id`, `operation_id`, `analysis` | 對 `alr-tw.legal-analysis/v1` 的六種可併用分支做 scope、民法要件／舉證責任、核心 dimensions、server-owned references 與 legal-context 檢查；不授權 final answer |

`research_legal_question.constraints.discovery_mode` 可為
`server_managed`（預設）或 `client_assisted`。後者必須在執行研究前登錄
`alr-tw.research-plan-proposal/v1`；前端 locator 只會成為候選，server 仍負責
official verification、evidence promotion 與 final decision。

`validate_legal_analysis` 只接受 references，不接受 source body、content
hash、`official=true` 或 client trust attestation。整份 analysis 固定為
`untrusted_client_proposal`，並支援 `civil_substantive`、
`civil_procedure`、`criminal_substantive`、`criminal_procedure`、
`administrative` 與 `constitutional_review` 六個可併用分支。行政法分支
再以 `legality`／`remedy` tracks 分流。`complete` 必須涵蓋分支核心 dimensions；
`issue_limited` 固定附帶 scope qualification。每個議題都要有 normative
source，確定的 `met`／`not_met` 結論另須 fact 或 eligible evidence；民法
每個 element 必須有一筆 burden-of-proof record。
v0.9.1 另允許五個 issue-oriented 分支攜帶 issue-level
`burden_of_proof`、`defenses`、branch-specific `procedural_posture` 與
`refusal_constraints`；民法分支沿用 element-level burden／defense schema。
這些仍是 `untrusted_client_proposal`，server 會把其 source、fact、evidence
重新送入既有 trust gate；refusal constraint 不能解除任何 blocker。
公開的 stateless validator 可由部署者傳入 server-owned `server_fact_states`；
內建 managed `ResearchService` 不保存 fact records，capabilities 會回報
`managed_fact_state_store_available=false`，因此 MCP caller 不能用自己提交
的 fact status 取得信任。未接自有 fact provider 時應使用 eligible evidence
IDs。

analysis tool 回傳的 `validated`／`qualified`／`blocked` 都只是
structure and trust decision，不是 final-answer decision，且固定：

- `authorizes_final_answer=false`；
- `semantic_entailment_performed=false`；
- `validation_scope=structural_and_trust_invariants_only`。

法律時點、authority status 與 legal validity 由
`alr-tw.legal-context-result/v1` provider contract 提供。公開套件只內建
explicit-allowlist synthetic fixture provider；live context 未確認時 fail
closed。

## v0.9.1 provider-neutral applicability and source contracts

除 MCP research tools 外，公開套件提供可替換的 provider contracts／facades：

| Contract | Location | Scope |
|---|---|---|
| `ApplicabilityResolver`／`validate_applicability_resolution` | `src/alr_tw/contracts/applicability.py`、`src/alr_tw/verification/applicability.py` | 以獨立 server-owned `server_source_ids` catalog binding 與 metadata 結構化解析特別／普通、上位／下位與新／舊來源；缺少 binding 或無法唯一確認時 fail closed，不執行 semantic entailment |
| `AuthorityLineageContract`／`validate_server_authority_lineage` | `src/alr_tw/contracts/authority_lineage.py`、`src/alr_tw/verification/authority_lineage.py` | 保存法院層級、程序姿態、上訴／審查鏈與 bounded negative-treatment；不產生 semantic opposition 或 consensus 結論 |
| `PublicLawProviderAdapter`／`GenericPublicLawProviderAdapter` | `src/alr_tw/contracts/public_law.py`、`src/alr_tw/providers/sdk.py` | 行政規則、行政解釋、訴願、立法資料及程序／救濟階段的 provider-neutral adapter；server metadata 缺失或不一致時禁止升格 |

這些介面由部署者接入自己的 provider；公開 repo 不附真實 corpus、index 或
production 參數。candidate、server-owned source 與 evidence 的信任層級仍由既有
verification／finalization gates 決定。

## v0.9.1 provider contracts

`HistoricalLawQuery`／`HistoricalLawResolution`／
`validate_server_historical_law` 提供立法院／其他官方歷史法規 provider 的
bounded port。查詢必須明示 `as_of_date` 與法規識別碼或名稱；resolution 會把
`HISTORICAL_STATUTE` 法條版本與 `LEGISLATIVE_MATERIAL` 立法資料分開保存。只有
server-owned、官方驗證且與 snapshot metadata 綁定的法條版本可作為
applicability resolver 的輸入；立法理由、委員會報告或議事紀錄不得直接當成法條。

`LegislativeHistoryProviderAdapter` 位於
`src/alr_tw/providers/legislative_history.py`，只定義 backend port 與 bounded
adapter，不內建立法院 endpoint、token、資料庫、索引或 production 參數。沒有
metadata issuer、source promoter、完整時點 scope 或法條版本時，結果維持
blocked／qualified，不能宣稱歷史法規已確認。

## v0.9.1 semantic-verifier plugin contract

公開套件提供 `alr-tw.semantic-verifier-request/v1`、
`alr-tw.semantic-verifier-result/v1` 與
`alr-tw.semantic-verifier-validation/v1`。插件只能針對 server-selected
target 回報 `supports`、`contradicts`、`uncertain` 或 `not_evaluated`；不能
建立 source／evidence、改變 source trust、升格 evidence、授權
`ordinary`／`validated` 或產生 final answer。結果一律標示
`advisory_only=true`，並由 `validate_server_semantic_verifier` 以獨立
server-owned target、source、evidence 與 run binding 重新檢查。

`run_server_semantic_verifier` 只提供 optional sidecar 執行邊界；插件例外、
schema 錯誤、foreign／stale reference 或 authority sentinel 偽造一律
blocked，不會被解讀為 `uncertain` 或 scoped absence。核心 runtime 不依賴
任何模型、prompt、embedding 或 semantic provider。

## v0.9.1 provider conformance and optional sidecar boundary

validate_provider_conformance 對 common ProviderResult 執行同一套
provider-neutral gate：server_source_ids、server_evidence_ids 與對應
server-owned object mapping 必須獨立注入；source 必須為新鮮的
official_verified／evidence_eligible，evidence 必須綁定可支援主張的 source。
candidate_only provider 永遠不能攜帶 source／evidence promotion。ERROR 只會
產生 retry blocker，NOT_FOUND 只有在明示 bounded scope 且完整覆蓋時才可作
scoped absence。

ReceiptAwareProviderAdapter 可接受部署者提供的 server receipt issuer，但不會
自行簽發或信任 receipt。只有同一 run 的完整 server-owned receipt set 通過
snapshot consistency，且所有 source／evidence gate 均通過時，才回報
ordinary_eligible；這個欄位仍不取代既有 finalization／answer validation。

SemanticSidecarRegistration 與 DeployerProviderDeclaration 是 optional
boundary contracts。sidecar 只能 shadow／advisory 執行，不能建立 evidence、改變
source trust、授權 finalization 或輸出可呈現答案。部署者 provider 的 corpus、模型、
credentials、private data 與 deployment parameters 均不得 bundled；公開 repo
只提供契約、validator 與 synthetic fixtures。

詳見 [Agent-neutral interoperability contract](INTEROPERABILITY_CONTRACT.md)。

## v0.9.1 server-managed tools

| Tool | Required input | Contract |
|---|---|---|
| `research_legal_question` | `query` | 建立 run；optional constraints: `as_of_date`, `research_depth`, `include_counter_authority`, `discovery_mode`, `retention` |
| `continue_legal_research` | `run_id`, `operation_id` | 原子執行一個 obligation；相同 operation id 回相同結果 |
| `get_legal_research_state` | `run_id` | 唯讀；無 provider call、無 TTL extension |
| `get_legal_research_finalization` | `run_id` | 回傳 server-owned `research_sufficiency`、Coverage v2、可選 provider snapshot receipts、answer mode、blockers 與 qualifications；這是 pre-draft／`safe_to_draft` 姿態，不授權呈現答案；structured refusal 由答案驗證拒答路徑回傳 |
| `lookup_legal_source` | `text` | 精確來源 lookup；可選 run/operation linkage；`claim_verified=false` |
| `validate_legal_answer` | `run_id`, `answer_text`, `operation_id` | 只用 server-owned evidence；核心主張應提供 optional `claim_bindings`；回 `validated`, `qualified`, `blocked` |
| `purge_research_storage` | `scope`, `confirm` | `scope=run` 需 `run_id`；同步清除 managed records |

`constraints.retention` 接受 `1s..7d` 或 `ephemeral`。`request_id`／`client_id` 是 correlation metadata，不是 authority 或 idempotency key；只有 `operation_id` 控制會改變狀態的重播。

`lookup_legal_source` 支援法規名稱＋條號、憲法裁判字號、完整 JID，以及含法院／年度／字別／號次的正式裁判字號。正式字號不唯一時回明確 ambiguity error，不猜測。

所有 tool 使用 `alr-tw.mcp_tool_result/v1` envelope。輸入採 `additionalProperties=false`；未知欄位與不支援的 MCP protocol version 都必須拒絕。MCP 保留欄位只相容 `params._meta` 與 direct `arguments._meta`，正規化後不進入業務參數、persistence 或 telemetry。

All MCP tool results are wrapped in:

```json
{
  "ok": true,
  "schema_version": "alr-tw.mcp_tool_result/v1",
  "data": {},
  "error": null
}
```

## v0.9.1 answer validation

`claim_bindings` 是 optional array；每筆包含 `claim_id`、`claim_text`、
`claim_type`、`importance`、至少一個同 run 的 `evidence_ids`，以及 v0.9.1
可選的 `issue_ids` 與 `citation_occurrences`。允許的 `claim_type` 是
`law_rule`、`court_view`、`disposition`、`fact`、`procedure`、`limitation`。

`citation_occurrences` 可提供 `evidence_id`、citation text 及 answer
start／end offsets。Server 會核對文字 occurrence、bound evidence、source
citation／identifier，並要求 citation 與 claim 位於同一 bounded clause。
這是 additive strict mode；未提供時維持 legacy caller 相容。

Server 會核對 evidence 存在、官方 trust status、expiry、claim-support eligibility 與 section role。核心法律 claim 沒有 span-level binding 時回 `CLAIM_CITATION_BINDING_REQUIRED`，不得以 run-wide 最高重疊通過。只傳 `answer_text` 的舊 caller 會取得 `binding_mode=legacy_unbound`。

若 run 已登錄外部研究計畫，所有 `requires_conclusion=true` 的 core issue
都必須出現在至少一筆 binding 的 `issue_ids`。這只證明明示覆蓋，不代表
semantic entailment。

答案驗證輸出為 additive `alr-tw.answer-validation/v4`，並揭露：

- `verification_method=deterministic_grounding_v2`；
- `semantic_entailment_performed=false`；
- `privacy`（local answer-output policy，不使用 outbound 180 字門檻）；
- `coverage_summary`；
- `binding_mode`。

`get_legal_research_finalization` 的結果是 server-owned
`alr-tw.finalization/v1`。`ready_for_draft` 只表示 workflow completion；
finalization 會依 sufficiency、Coverage v2、required evidence、counter
authority scope、snapshot consistency 與 privacy 結果計算答案姿態。`ordinary`
必須是 sufficient 且具完整必要證據；`conditional` 必須帶不可省略的
qualification；`refusal_only` 只允許答案驗證拒答路徑回 structured refusal，不回草稿。synthetic
fixture 不能支撐法律答案，counter `not_found_in_scope` 不能證明全球不存在
反面見解或實務一致。

Snapshot receipt 是 provider-neutral contract，不表示 bundled provider 已簽發
receipt。v0.9.1 內建 `ResearchService` 尚未注入或持久化 live-provider generation
receipt，因此 built-in live output 最多為 `conditional`／`qualified`；`ordinary`
只保留給 receipt-aware provider adapter 完成同一 run 的 server-owned binding。

## Tools

| Tool | Purpose | Final citation effect |
|---|---|---|
| `agentic_legal_research` | Synthetic agentic RAG loop returning `alr-tw.agentic_trace/v1` | Reports final citations |
| `run_agentic_demo` | Deterministic ALR-TW scenario trace | Reports final action |
| `begin_agentic_run` | Begin recording an externally driven tool run | Opens a server-side run state |
| `finalize_agentic_run` | Assemble and gate a recorded externally driven tool run | Computes final action |
| `get_claim_grounding_policy` | Returns the current claim-grounding contract | No direct citation effect |
| `extract_answer_claims` | Split an answer into deterministic public claim units | No direct citation effect |
| `check_claim_support` | Check answer claims against evidence segments and return semantic grounding summary | No direct citation effect |
| `build_validation_report` | Markdown validation report | No direct citation effect |
| `get_trust_model` | Source tiers and trust policy | No direct citation effect |
| `legal_search` | Synthetic search demo | Candidate retrieval only |
| `validate_citation` | Validate citation tier and use | Determines final eligibility |
| `exact_law_lookup` | Synthetic exact law lookup | Demo only |
| `exact_judgment_lookup` | Synthetic exact judgment lookup | Demo only |
| `exact_constitutional_lookup` | Synthetic exact constitutional lookup | Demo only |

Invalid JSON-RPC params use protocol errors. Tool outputs use stable schema
versions and fixed error codes when an ALR-TW trust decision fails.

## Trace Output

`agentic_legal_research` and `run_agentic_demo` return the canonical public trace
schema: `alr-tw.agentic_trace/v1`.

Public example tool calls are deterministic harness records. Their
`execution_mode` is `harness_recorded`; they are not live external tool logs.

## Externally Driven Run Recording

The legacy externally-driven flow uses Design A: session-recorded run state. `McpSession` already owns the
stdio request lifecycle, so the server can keep one open run per session without
invasive changes. This design records and gates externally driven tool runs
because the server observes the actual MCP `tools/call` requests before it
assembles the trace. Design B was not used because a submitted transcript would
prove less about tool invocation.

Flow:

1. `begin_agentic_run` accepts only `query` and returns `run_id`.
2. While the run is open, the server records successful calls to
   `legal_search`, `validate_citation`, `exact_law_lookup`,
   `exact_judgment_lookup`, `exact_constitutional_lookup`,
   `extract_answer_claims`, and `check_claim_support`.
3. Recorded calls become `ToolCallTrace` entries with `execution_mode:
   "actual_tool"`.
4. `finalize_agentic_run` accepts only `run_id` and `answer`, assembles
   evidence from recorded `validate_citation` outputs, computes coverage from
   server-observed validation inputs, reuses the deterministic trust-gate path,
   and returns `alr-tw.agentic_trace/v1` with `trace_kind:
   "externally_driven"`.

An externally driven run reaches `answer` only if the client recorded a
`check_claim_support` step whose result is safe; a run with a final citation
but no claim-support step routes to `human_review_required` because claim
grounding is not optional for a presentable answer.

This repository still ships no LLM and no agent implementation. The external
MCP client supplies the agent role; ALR-TW records and gates externally driven
tool runs.

## Non-Bypass Rules

The following fields are always computed server-side:

- `final_action`
- `trust_gate.safe_to_present`
- `citation_use`
- `identifier_resolution`

If a client supplies any of these fields in tool arguments where the schema does
not allow them, the server returns JSON-RPC `-32602` for unexpected or invalid
arguments.

Client-supplied `answer` text is retained in the trace only when the trust gate
passes with `final_action == "answer"` and `safe_to_present == true`. Otherwise
the trace contains `answer: null`.

Source tier semantics are unchanged. `synthetic` remains demo-only,
`external_semantic_recall` remains candidate-only, and `verified_cache` keeps
the existing opt-in identifier-backed rules. Identifier resolution is recomputed by
the server-side synthetic resolver when the opt-in is enabled.

## Citation Validation Metadata

`validate_citation` accepts:

- `citation_id`
- `source_tier`
- optional `official_url`
- optional `official_identifier`
- optional `official_hash`
- optional `verified_at`
- optional `source_label`
- optional `legal_material_type` (`judgment`, `law`, or `constitutional`)

`verified_cache` becomes final-eligible when it has an official URL, an
official content hash, and a verification time. Otherwise it fails closed.

Identifier-backed verified cache is a separate, opt-in capability
(`ALR_TW_IDENTIFIER_BACKED_VERIFIED_CACHE`, default off). When enabled, an
`official_identifier` may substitute for the official URL only for
judgment-type records, and only after the server-side resolver maps the
identifier to a locally stored official original record and the recomputed
content hash matches `official_hash`. The resolution status is computed by the
server; callers cannot declare it, and a bare identifier with a fabricated
hash is rejected with `IDENTIFIER_UNRESOLVED` or `IDENTIFIER_HASH_MISMATCH`.
The public server carries only a synthetic demo resolver.

That server-side rule is scoped to the MCP surface. At the Python library level,
`identifier_resolution` is part of the adapter/verifier trust boundary and must
only be set by the deployer's resolver layer, such as
`resolve_identifier_citation`; setting it by hand is vouching for the record.

`citation_eligibility` still describes source-tier eligibility only.
`check_claim_support` provides explicit claim-grounding status with
`supported` / `partially_supported` / `overstated` / `unsupported` / `contradicted`
and can be used by clients to decide whether human review is needed.
