# ALR-TW Agentic Workflow

This repository does not ship an LLM or agent implementation. The external client supplies planning and drafting; the server owns research state and trust decisions.

## v0.10.0 agent-neutral client-assisted workflow

1. 呼叫 `get_legal_research_capabilities`，不得假設 provider 或研究能力存在。
2. 以 `discovery_mode=client_assisted` 建立 run。
3. 外部 client 提出爭點與法源 locator，呼叫 `submit_legal_research_plan`。
4. Server 將 plan 固定為 `untrusted_client_proposal`，並拒絕 client evidence／trust decision。
5. Law／judgment／constitutional locator 由 server 執行 official exact lookup。
6. 若前端產生結構化法律分析，將民法、民事程序、刑法、刑事程序、
   行政法與憲法審查所需分支放入同一信封，再呼叫
   `validate_legal_analysis`。Server 只核對結構、scope、normative source、
   fact／evidence references 與 legal context。
7. 外部 client 以 server evidence 起草，並把 claim 綁定到 evidence ID 與 issue ID。
8. 呼叫 `get_legal_research_finalization` 讀取 server-owned Coverage v2、
   `research_sufficiency`、`answer_mode`、snapshot receipts、blockers 與
   qualifications；structured refusal 由拒答的答案驗證路徑產生。
9. `validate_legal_answer` 同時執行 evidence、role、time、privacy、claim 及 issue coverage gates；
   finalization 的 `refusal_only` 不得輸出草稿。

`client_assisted` 不代表 client 擁有 verification。它只改變初始 locator
來源；任何 analysis `validated` 也不代表實體涵攝或 final answer 已通過。
兩者都不能改變 server-owned trust boundary。詳見
[Interoperability Contract](INTEROPERABILITY_CONTRACT.md)。

v0.10.0 另提供 provider-neutral applicability、authority／judgment-lineage 與
public-law contracts，以及可替換 provider SDK。它們只承載 server-owned
metadata、來源角色、時點、程序及 bounded 關係；不能從來源文字推導法律效果，
也不能把 `not_found_in_scope` 轉成全球不存在或實務一致。

Provider-neutral snapshot receipts are an adapter contract. The bundled
`ResearchService` does not yet issue or persist live-provider generation
receipts, so built-in live runs remain at most `conditional`／`qualified`;
`ordinary` requires a receipt-aware provider adapter bound to the same run.
Finalization is pre-draft (`safe_to_draft`) only; presentation still requires
`validate_legal_answer`.

## v0.10.0 server-managed workflow

1. `research_legal_question` 建立 run 與固定順序 obligations，不生成答案。
2. Agent 重複呼叫 `continue_legal_research`；每次只執行一個 obligation，並使用唯一 `operation_id`。
3. `get_legal_research_state` 唯讀觀察，不觸發 provider 或延長 TTL。
4. `lookup_legal_source` 只做精確來源查詢；帶 `run_id` 時 server 才把官方 snapshot 連結到該 run。
5. 非 final obligations 完成後，run 進入 `ready_for_draft`；這只代表 workflow completion，
   不代表 research sufficiency。
6. Agent 先讀 `get_legal_research_finalization`；server 以 sufficiency 與 answer mode
   決定 ordinary、conditional 或 refusal-only 姿態。
7. Agent 起草並呼叫 `validate_legal_answer`；server 只使用 run-owned、fresh、eligible evidence。
8. Finalization 只提供起草前姿態；只有 `validate_legal_answer` 回傳的
   `validated`／`qualified` 可展示；`blocked` 或 `refusal_only` 必須丟棄草稿並回傳結構化限制。
9. `ephemeral` run 在 validation 回傳後同步 purge；其他 run 依 TTL 或明確 purge 清除。

Agent 不能自行把 obligation 標完成、加入 evidence、改 source role、延長 TTL 或宣告 final decision。

ALR-TW is an MCP harness that constrains an external MCP client and records and
gates externally driven tool runs. This repository does not ship an LLM or agent implementation.
Planning, tool selection, and natural-language reasoning are supplied by the
caller, such as an external MCP client or LLM runtime; ALR-TW provides tool
interfaces, deterministic gate graphs, traces, and report contracts that
constrain that external client.

```text
Query
  -> Query Understanding
  -> Source Plan
  -> Retrieval
  -> Source Classification
  -> Citation Validation
  -> Coverage Gate
  -> Trust Gate
  -> Final Decision
```

The graph is deterministic. Every final answer must pass citation validation and
the trust gate; otherwise the harness refuses or requires human review. The
trust-gate decision is made by the deterministic harness, not asserted by the
external client.

Public example traces are deterministic harness traces. Their `tool_calls` use
`execution_mode: "harness_recorded"` and should not be read as live external
tool execution logs.

Session-recorded traces from `begin_agentic_run` / `finalize_agentic_run` use
`trace_kind: "externally_driven"` and record tool calls with `execution_mode:
"actual_tool"`.

Clients should render answer content only when `trust_gate.safe_to_present` is
true and `final_action` is `answer`.

## Scenarios

- `pass_official_source`: final citation exists and the trust gate allows answer.
- `fail_candidate_only`: external semantic recall remains candidate-only.
- `fail_synthetic_only`: synthetic data is demo-only and cannot become final law.
- `fail_verified_cache_incomplete`: verified cache missing required metadata is rejected.
- `fail_no_final_citation`: no final citation produces fail-closed refusal.
- `fail_low_coverage`: low legal coverage blocks final answer.
- `human_review_required_claim_support`: source exists, but claim support was not checked.
- `pass_claim_supported`: source exists and claim is supported by legal segments.
- `fail_party_argument_as_court_view`: party-argument segment is misread as court-view.
- `fail_overstated_case_specific_rule`: claim over-generalized a case-specific finding.
- `fail_unsupported_paraphrase`: claim paraphrase does not match supporting segments.
- `human_review_claim_unchecked`: source exists, but claim support was intentionally unchecked.
