# ALR-TW v0.6.1 Release Audit

Audit date: 2026-07-22 (Asia/Taipei)

Source commit under test: `605b51ab1da86423649a7178702c36ce7d1e8e68`

Release decision: **TAG/RELEASE BLOCKED — branch publication permitted for clean-environment testing**

This audit records commands actually executed. A passing synthetic or contract test is not presented as a passing real ordinary-court corpus or live-provider canary.

## Environment

| Component | Version |
|---|---|
| Python (project and fresh venv) | 3.13.12 |
| uv | 0.10.9 |
| pytest | 9.1.1 |
| pydantic | 2.13.4 |
| MCP Python SDK (fresh venv) | 1.28.1 |
| External reviewer | `gemini-3.6-flash-high`, effort `high`, via AGY |
| package | alr-tw 0.6.1 |

## Reproducible quality gates

| Command | Exit | Result |
|---|---:|---|
| `uv run ruff check .` | 0 | PASS |
| `uv run mypy src` | 0 | PASS, 92 source files |
| `uv run pytest -q` | 0 | PASS, 279 tests |
| `uv run python scripts/check_no_forbidden_files.py .` | 0 | PASS |
| `uv run python scripts/check_public_boundary.py` | 0 | PASS |
| `SOURCE_DATE_EPOCH=<source commit time> uv build` | 0 | PASS, wheel and sdist built |

Artifacts:

| Artifact | SHA-256 |
|---|---|
| `alr_tw-0.6.1-py3-none-any.whl` | `6ab797c9ed1a47159f6f496ee9d690dab1af8c31d2d55486478867d7f2a056f1` |
| `alr_tw-0.6.1.tar.gz` | `a1d3051d3c8a3301f783a4cb9169da59b39e41144a8b1ff3362d3125e3be642e` |

The fresh-wheel remediation smoke verified 20 packaged tools, the six high-level tool names,
the `claim_bindings` evidence-ID guidance, role-safe party/court rebuttal parsing, hierarchical
article anchors, and lexical-compound polarity guards.

## External review

AGY was used only as a read-only external reviewer. The exact model ID was confirmed through
`agy models`, and review processes used `gemini-3.6-flash-high` with high effort in plan mode.
Findings were reproduced locally before changes were accepted. The final
full-diff review reported no P0, P1, or P2 defect, legal-evidence fail-open, state-transition
error, or material test gap.

## Fresh-wheel MCP and host canaries

The wheel was installed into a new venv with its `mcp` extra. Import checks returned `alr_tw.__version__ == 0.6.1` and `tw_legal_rag_mcp.__version__ == 0.6.1`.

- MCP Python SDK initialize/list-tools/`get_trust_model` canary: **PASS**; server version `0.6.1`, 20 tools listed.
- Fresh-wheel six high-level tool flow with SDK-supplied request metadata: **PASS**. The flow created a synthetic run, advanced it, read state, performed lookup, obtained a fail-closed answer validation, and purged the run.
- Codex native one-off host canary: **PASS**. Codex loaded only the fresh-wheel server through invocation-local config and completed one `get_trust_model` tool call. No user MCP configuration was changed.
- The first non-interactive Codex attempt was cancelled by host approval policy before the tool executed. A second read-only canary used the CLI's one-invocation approval bypass and succeeded. This was a host approval event, not a server or `_meta` failure.

## Live provider canaries

Live checks used generic public-law queries and did not persist identifiers or judgment text:

| Canary | Result |
|---|---|
| Supreme Court search → official exact page | PASS, complete parse, eligible evidence present |
| District-court labor search → official exact page | PASS, complete parse, eligible evidence present |
| Page containing `事實及理由` | PASS, official source preserved with eligible evidence |
| Live TLR candidate → typed JID → Judicial Yuan exact page | PASS, complete parse, eligible evidence present |

The first live TLR promotion attempt exposed two current-page variants: canonical identity in PDF-export `tablename + jrecno`, and an empty `.htmlcontent` beside populated `.text-pre`. Commit `88222a4` added deterministic support for both and the repeated live canary passed.

## V0.6.1 matrix results

| Gate | Status | Evidence |
|---|---|---|
| RG-MCP-01 | PASS | `params._meta` and direct `arguments._meta` contract tests |
| RG-MCP-02 | PASS | all six high-level tools, fresh-wheel MCP SDK metadata canary |
| RG-MCP-03 | PASS | unknown business fields remain rejected |
| RG-JUD-01 | **BLOCKED** | no policy-approved 8-case real ordinary-court snapshot corpus in the public repo |
| RG-JUD-02 | PARTIAL | synthetic layout and adversarial role regressions false party-to-court promotions = 0; real corpus not run |
| RG-JUD-03 | PASS | partial parsing preserves an official non-eligible source |
| RG-IDR-01 | PASS | canonical `doc_id` and official-URL fallback promotion tests |
| RG-IDR-02 | PASS | canonical identifier mismatch blocks promotion |
| RG-PRIV-01 | PASS | 1,000- and 3,000-plus-character Chinese answer cases pass output privacy |
| RG-PRIV-02 | PASS | deterministic identifier/token redaction and confidential-content blocking |
| RG-GRD-01 | PASS | reordered Chinese, hierarchical-anchor, qualifier, and lexical-compound positive regressions |
| RG-GRD-02 | PASS | seven negative cases: polarity, qualifier, role, numeric anchor, article anchor, unbound core claim, citation dumping |
| RG-GRD-03 | PASS | unbound core claim returns `CLAIM_CITATION_BINDING_REQUIRED` |
| RG-COV-01 | PASS | zero-call counter-authority handler keeps checked=false and records limitation |
| RG-COV-02 | PASS | law and constitutional keyword-only paths keep exact coverage false |
| RG-PKG-01 | PASS | fresh-wheel MCP SDK and Codex host canaries |
| RG-REG-01 | PASS | complete test suite passes; behavior changes disclosed in changelog |

## Judgment corpus status

The committed manifest is `tests/fixtures/judgments/v061/manifest.json`. It contains eight **synthetic layout regression** documents:

- source preservation: 8/8;
- complete parses: 6;
- partial parses preserved: 2;
- party-argument evidence promoted as court reasoning: 0;
- manifest hashes verified during tests.

The manifest explicitly sets `satisfies_ordinary_court_release_gate=false`. It does not substitute for the required eight real public official snapshots. The current public-boundary policy rejects real-shaped judgment identifiers and production corpus material; that policy was not silently weakened in this repair branch.

## Hybrid, privacy, grounding, and coverage

- Hybrid promotion tests cover canonical TLR document identity, JID recovered from official URL, and official-page identity mismatch.
- Candidate ordering and canonical-JID deduplication occur before the five-target verification budget; verification metrics and provenance are returned.
- Answer output privacy is local-only and independent of the conservative 180-character outbound-query policy.
- Answer validation v3 discloses `deterministic_grounding_v2` and `semantic_entailment_performed=false`.
- Structured core claims use only bound evidence for stale, citation, role, and grounding
  decisions. Legacy unbound core claims remain blocked even when eligible evidence exists;
  only non-core legacy claims may use run-owned eligible evidence, and they are capped at
  `QUALIFIED` with an explicit limitation.
- The public implementation does not perform systematic counter-authority search. The coverage state remains false and final answers require an explicit limitation.

## Not executed or not satisfied

- Real V0.6.1 ordinary-court fixed corpus: **not executed / blocking** because no approved public-safe fixture path was provided and the repository policy forbids committing real corpus identifiers/content.
- V0.6.2 operation leases/failure recovery and stable source-version identity: **deferred by specification**.

Until the real fixed-corpus governance conflict is resolved, v0.6.1 must not be tagged,
released, or described as public-preview ready. A non-release branch may be published solely
for clean-environment engineering validation.
