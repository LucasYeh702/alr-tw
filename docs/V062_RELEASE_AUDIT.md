# ALR-TW v0.6.2 Release Audit

Audit date: 2026-07-23 (Asia/Taipei)

Release decision: **IMPLEMENTATION VERIFIED; NOT YET TAGGED OR PUBLISHED**

## Scope

v0.6.2 is a compatibility hotfix. It does not add natural-language statutory issue
planning, systematic counter-authority search, or a redesigned research-sufficiency
state machine.

The audited changes are:

- legacy Judicial Yuan `hlExportPDF?type=JD&id=...` and
  `/EXPORTFILE/ExportToPdf.aspx?type=JD&id=...` identity extraction;
- official canonical completion or explicit legacy verification for five-part TLR
  document IDs;
- direct-result and link-only official search page fallbacks;
- current-day `as_of_date` handling;
- bounded local TLR relevance reranking before official verification;
- package, MCP server, documentation, and user-agent version alignment.

## Safety invariants

- The requested identifier must still match the identifier recovered from the official
  page.
- A five-part document ID is never completed by guessing a version suffix. A valid
  six-part canonical JID is accepted only when its first five parts match exactly; a
  legacy page that only exposes the same five-part identifier remains explicitly typed
  as `legacy_five_part_jid`.
- A six-part request cannot be verified by a five-part page marker. This fails closed as
  `LEGACY_JUDGMENT_IDENTIFIER_AMBIGUOUS`; a five-part page without a verifiable marker
  fails as `LEGACY_JUDGMENT_IDENTIFIER_UNRESOLVED`.
- A TLR result remains an external candidate and cannot support a claim before successful
  Judicial Yuan exact lookup and evidence promotion.
- Reranking only changes which candidates consume the five-target verification budget.
- The local reranker bounds the query to 512 characters and candidate text to 8,192
  characters before generating 2–4 character n-grams.
- Search HTML variants that cannot produce a valid official JID still fail closed.

## Verification results

| Gate | Result |
|---|---:|
| Legacy-ID provider, integration, and resolver tests | 47 passed |
| Full pytest suite | 293 passed |
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

On 2026-07-23, two reported public legacy pages whose only machine-readable identity was
the same five-part `/EXPORTFILE/ExportToPdf.aspx` marker both completed exact lookup as
`legacy_five_part_jid`. The probe persisted neither judgment text nor real identifiers.
The committed regression fixture preserves that observed DOM shape with a synthetic ID
and synthetic content.

This is a point-in-time canary, not a claim that Judicial Yuan HTML, WAF behavior, or
recall will remain stable.

## Build artifacts

| Artifact | SHA-256 |
|---|---|
| `alr_tw-0.6.2-py3-none-any.whl` | `5ec46c80da0e487d78d8d44195b25ec4463989c458374ed86f50be0b571dcb7d` |
| `alr_tw-0.6.2.tar.gz` | `d55f93bf09a911736a21b0d50508124a3ee46ea786e0376dba9218a958675a31` |

## Remaining disclosed limitations

- Natural-language legal issues without a statute name and article number may still end
  with `LAW_KEYWORD_RESULTS_REQUIRE_EXACT_LOOKUP`.
- `COUNTER_AUTHORITY_SEARCH_NOT_IMPLEMENTED` remains accurate.
- `ready_for_draft` remains a workflow-completion state rather than a complete research
  sufficiency judgment.
- The TLR reranker is a deterministic local prioritizer, not semantic entailment or a
  substitute for official verification.
