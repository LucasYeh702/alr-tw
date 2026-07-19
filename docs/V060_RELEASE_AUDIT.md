# ALR-TW v0.6.0 Release Audit

Audit date: 2026-07-19 (Asia/Taipei)

Release decision: **public-preview ready**.

This record captures checks actually executed against the v0.6.0 working tree and a
freshly installed release artifact. It is not a statement that every external service
will remain available, and it is not a legal-accuracy benchmark.

## Scope and trust decision

- The recommended path is the server-owned research service and its six v0.6 MCP
  tools.
- `synthetic` remains the safe default. Live access requires an explicit data mode.
- TLR is candidate-only semantic recall. Its output cannot become answer evidence until
  independently resolved and verified against an official source.
- Ordinary judgments are searched and downloaded directly from the public Judicial Yuan
  judgment search and detail pages. This path does not use JDoc or require an API token.
- `mcp-taiwan-legal-db` is not a dependency or integrated component. No source code was
  copied from it.

The audit applies to the source snapshot published under the `v0.6.0` tag. The tag and
GitHub Release remain the canonical public record of the exact release commit.

## Source-tree quality gates

The following commands passed on the audited working tree:

```text
uv run ruff check .
uv run mypy src
uv run pytest -q
python3 scripts/check_no_forbidden_files.py
python3 scripts/check_public_boundary.py
git diff --check
```

Observed result:

- Ruff: passed.
- Mypy: 88 source files checked, no issues.
- Pytest: 227 passed.
- Forbidden-file scan: passed.
- Public/private boundary scan: passed.
- Patch whitespace validation: passed.

The caller-self-attestation regression suite also passed: 9 tests passed, including
rejection of caller-supplied `official` and `verified_cache` assertions, resolver hash
mismatch, missing resolver proof, and non-judgment identifier-backed cache promotion.

## Distribution audit

Built from the source tree with `uv build`, then installed into a new Python 3.11 virtual
environment using the wheel's `[all]` extra.

Artifacts:

| Artifact | Size | SHA-256 |
| --- | ---: | --- |
| `alr_tw-0.6.0-py3-none-any.whl` | 113 KiB | `5db564d842f3fcaf2700d0faf224c7ee2dc788fe414afb8c121bfe0e9d2a4530` |
| `alr_tw-0.6.0.tar.gz` | 88 KiB | `b086a5d5371ede6c37b324de282ce4c51fa452db52bc4b681db2f44889ee87ba` |

Fresh-install checks:

- `alr_tw.__version__ == 0.6.0`.
- `tw_legal_rag_mcp.__version__ == 0.6.0`.
- `alr-tw doctor` passed with the safe `synthetic` default and reported
  `judicial_source: public_website_html`.
- MCP Python SDK 1.28.1 initialized the packaged server and listed 20 tools.
- All six v0.6 high-level tools were present.
- Protocol versions `2025-11-25`, `2025-06-18`, `2025-03-26`, and `2024-11-05`
  completed initialization; an unknown version was rejected.
- A packaged end-to-end synthetic research run reached a blocked decision with
  `answer_text: null`, and `purge_research_storage(scope="all")` succeeded.

## Public live smoke checks

Public, read-only smoke checks from the freshly installed wheel passed:

- Laws and Regulations Database: `B0000001:1052` was resolved and produced an
  evidence-eligible official span.
- Constitutional Court: `113年憲判字第8號` was resolved with 35 separately typed
  evidence spans.
- TLR: health was `healthy`; a safe query returned two
  `external_semantic_recall` / `external_candidate` records and no evidence IDs.
- Judicial judgment health was `healthy`; a public, non-personal keyword query returned
  three `official_search_result` candidates.
- A public Supreme Court civil citation resolved unambiguously to its canonical official
  identifier, downloaded the official detail page, and produced 24 separately typed
  evidence spans. The source-tree live run took 445 ms and the packaged
  wheel run took 927 ms on this network; source-tree health and keyword calls took 134 ms
  and 594 ms respectively. These are smoke timings, not benchmark guarantees.

## Clean-room comparison

The public `mcp-taiwan-legal-db` repository was cloned read-only at commit
`f324c00dc87eb49501cf0282433158ddb691f226`. ALR-TW's two judgment implementation files
were compared against its search, document, WAF, and parser modules after removing blank,
comment, and import lines:

- maximum token-sequence similarity: 7.45%;
- maximum exact substantive-line block: two lines;
- the two-line matches were generic Python syntax or unavoidable Judicial Yuan interface
  fields such as `judtype=JUDBOOK` and the official submit control;
- no matching implementation block of three or more substantive lines was found.

This is evidence against direct copying for the audited versions, not a universal
copyright or provenance guarantee. The implementation remains structurally independent:
an operation-scoped fixed-host transport feeds pure HTML parsers, provider contracts,
server-owned evidence snapshots, and the existing resumable research store. It does not
import or execute the reference project.

## Ordinary-judgment performance and failure behavior

- One operation reuses an HTTPS client, TLS connection, and ASP.NET cookies, then discards
  the session when the operation ends.
- Exact formal citations use one cross-system query when the material type is not stated;
  ambiguous results fail closed instead of issuing four sequential system queries.
- Precise case-word/number searches use GET directly; keyword searches perform one form
  GET, one POST, and one result-list GET.
- Candidate parsing stops at the configured cap (maximum 20), and verified source
  snapshots are reused through the server-owned 24-hour TTL store.
- Redirects, response bytes, timeouts, input lengths, hosts, and result counts are bounded.
- WAF/rejection pages return `OFFICIAL_SOURCE_BLOCKED`; the project does not attempt
  CAPTCHA or WAF evasion and does not convert transport failure into “not found.”

## Release interpretation

The v0.6.0 artifact is suitable for a public preview of the trust harness, provider
contracts, resumable research workflow, storage/purge controls, and fail-closed answer
validation. It must not be described as a complete Taiwan-law corpus, a substitute for
professional legal advice, or proof of substantive legal-answer quality.
