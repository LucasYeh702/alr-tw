---
title: "[RFC] Bounded Verified Quick Research for Prompt-Selected Fast Case Retrieval"
labels: ["enhancement", "mcp", "legal-safety", "v0.12"]
state: "accepted-for-v0.12-candidate"
author: "ALR-TW Maintainers"
target_repo: "LucasYeh702/alr-tw"
---

# [RFC] Bounded Verified Quick Research

## 1. Summary

Add a prompt-selectable `quick` research mode for questions whose main task is
finding judgments. Quick mode reduces breadth and orchestration overhead; it does
not relax source authenticity.

Supported leading commands are:

```text
/quick 請查找定型化契約條款效力的相關裁判
快速模式：請查找定型化契約條款效力的相關裁判
```

The structured `constraints.research_depth="quick"` input remains supported. A
prompt command that conflicts with the structured constraint is rejected.

## 2. Query-aware obligation plan

For a judgment-retrieval query, quick mode schedules only:

1. query understanding;
2. outbound privacy screening when `hybrid_verified` is active;
3. candidate recall;
4. exact Judicial Yuan verification of at most five ranked candidates;
5. evidence sufficiency;
6. separate final-answer validation after the external agent drafts.

An explicitly cited statute remains in scope. Counter-authority expansion,
lineage inspection, historical-law expansion, and semantic opinion comparison
are not added by default. Standard and deep modes keep their broader plans.

## 3. Verification and answer posture

- TLR, local search, and other recall adapters return candidates only.
- In `hybrid_verified`, quick mode queries the configured semantic candidate
  provider first and falls back to Judicial Yuan keyword search only when that
  provider fails or yields no usable candidate.
- Each selected judgment must be resolved to a formal citation or canonical JID
  and checked against the Judicial Yuan source. A catalog-bound local snapshot
  may satisfy the same exact-content gate; otherwise the provider falls back to
  the Judicial Yuan website.
- If no candidate passes exact verification, the run stays `refusal_only`.
- Similar-case quick research always retains a bounded top-K qualification. If
  at least one candidate passes, the verified set may proceed only as
  `qualified` / `conditional`; rejected or budget-truncated candidates add
  audit limitations. It cannot support global absence, completeness, finality,
  or consensus claims.
- `ready_for_draft` does not authorize presentation. The drafted answer still
  must pass same-run claim/evidence binding through `validate_legal_answer`.

## 4. Single-roundtrip execution and measurement

`execute_legal_research` creates a run and advances all currently executable
server-owned obligations in one bounded call. It preserves per-step operation
records, stops on retryable provider failure or an external-plan gate, and never
auto-runs final-answer validation. The response includes overall and per-step
`elapsed_ms` plus a maximum-five-source verified evidence bundle when ready for
drafting.

## 5. Acceptance scenario

The public acceptance fixture is intentionally generic:

> 請查找定型化契約條款效力的相關裁判

Acceptance requires the system to use bounded candidate recall, verify every
returned case number and quoted content before promotion, expose no more than
five verified judgments, disclose all truncation or failed-verification limits,
and complete without requiring the MCP client to clock each obligation manually.

Timing is an operational measurement, not a correctness claim. Live-provider
availability and network latency remain outside the deterministic CI contract.
