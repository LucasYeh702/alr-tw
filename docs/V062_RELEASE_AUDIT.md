# ALR-TW v0.6.2 Release Audit

Audit date: 2026-07-22 (Asia/Taipei)

Release decision: **IMPLEMENTATION VERIFIED; NOT YET TAGGED OR PUBLISHED**

## Scope

v0.6.2 is a compatibility hotfix. It does not add natural-language statutory issue
planning, systematic counter-authority search, or a redesigned research-sufficiency
state machine.

The audited changes are:

- legacy Judicial Yuan `hlExportPDF?type=JD&id=...` and
  `/EXPORTFILE/ExportToPdf.aspx?type=JD&id=...` canonical JID extraction;
- official canonical completion for five-part TLR document IDs;
- direct-result and link-only official search page fallbacks;
- current-day `as_of_date` handling;
- bounded local TLR relevance reranking before official verification;
- package, MCP server, documentation, and user-agent version alignment.

## Safety invariants

- The requested JID must still match the canonical JID recovered from the official page.
- A five-part document ID is never completed by guessing a version suffix. The official
  page must return a valid six-part canonical JID whose first five parts match exactly.
- A TLR result remains an external candidate and cannot support a claim before successful
  Judicial Yuan exact lookup and evidence promotion.
- Reranking only changes which candidates consume the five-target verification budget.
- The local reranker bounds the query to 512 characters and candidate text to 8,192
  characters before generating 2–4 character n-grams.
- Search HTML variants that cannot produce a valid official JID still fail closed.

## Verification results

| Gate | Result |
|---|---:|
| Targeted v0.6.2 and release-hardening tests | 96 passed |
| Full pytest suite | 289 passed |
| Ruff | passed |
| mypy (`src`, 92 source files) | passed |
| Forbidden-file scan | passed |
| Public-boundary scan | passed |
| Source distribution and wheel build | passed |
| Fresh-wheel imports | `alr_tw == tw_legal_rag_mcp == 0.6.2` |
| Fresh-wheel MCP surface | server `0.6.2`, 20 tools |
| Fresh-wheel `alr-tw doctor` | passed in safe synthetic mode |

## Live Judicial Yuan canary

The public query `試用期間 解僱 資遣費`, constrained to civil cases, returned five
official candidates on 2026-07-22. All five completed official exact lookup and evidence
promotion successfully in approximately 3.2 seconds.

This is a point-in-time canary, not a claim that Judicial Yuan HTML, WAF behavior, or
recall will remain stable.

## Build artifacts

| Artifact | SHA-256 |
|---|---|
| `alr_tw-0.6.2-py3-none-any.whl` | `0858fb20a7e9213a969de29bad86c73206b9f939cec7b18d9fb21fce8721663d` |
| `alr_tw-0.6.2.tar.gz` | `caa442e699238a5c10bbf8b74fc084313d2bd869a542ea3982b7aebf2359a625` |

## Remaining disclosed limitations

- Natural-language legal issues without a statute name and article number may still end
  with `LAW_KEYWORD_RESULTS_REQUIRE_EXACT_LOOKUP`.
- `COUNTER_AUTHORITY_SEARCH_NOT_IMPLEMENTED` remains accurate.
- `ready_for_draft` remains a workflow-completion state rather than a complete research
  sufficiency judgment.
- The TLR reranker is a deterministic local prioritizer, not semantic entailment or a
  substitute for official verification.
