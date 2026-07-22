# ALR-TW v0.6.1 Release Audit

Audit date: 2026-07-22 (Asia/Taipei)  
Source commit under test: `4eb60381f2b7ab445d0f0759e7d8dcb999eba7e1`  
Release decision: **BLOCKED — do not tag or publish yet**

This audit records commands actually executed. A passing synthetic or contract test is not presented as a passing real ordinary-court corpus or live-provider canary.

## Environment

| Component | Version |
|---|---|
| Python (project and fresh venv) | 3.13.12 |
| uv | 0.10.9 |
| pytest | 9.1.1 |
| pydantic | 2.13.4 |
| MCP Python SDK (fresh venv) | 1.28.1 |
| Codex host | codex-cli 0.144.3 |
| package | alr-tw 0.6.1 |

## Reproducible quality gates

| Command | Exit | Result |
|---|---:|---|
| `uv run ruff check .` | 0 | PASS |
| `uv run mypy src` | 0 | PASS, 92 source files |
| `uv run pytest -q` | 0 | PASS, 265 tests |
| `uv run python scripts/check_no_forbidden_files.py .` | 0 | PASS |
| `uv run python scripts/check_public_boundary.py` | 0 | PASS |
| `uv build` | 0 | PASS, wheel and sdist built |

Artifacts:

| Artifact | SHA-256 |
|---|---|
| `alr_tw-0.6.1-py3-none-any.whl` | `43e1d582d09e45d99c0ac000c51ae06774417771f116b83148ebc10094a77f24` |
| `alr_tw-0.6.1.tar.gz` | `e22786cd6e3c11774c607051170326208effbb30791c025e941aedb836983106` |

## Fresh-wheel MCP and host canaries

The wheel was installed into a new venv with its `mcp` extra. Import checks returned `alr_tw.__version__ == 0.6.1` and `tw_legal_rag_mcp.__version__ == 0.6.1`.

- MCP Python SDK initialize/list-tools/`get_trust_model` canary: **PASS**; server version `0.6.1`, 20 tools listed.
- Fresh-wheel six high-level tool flow with SDK-supplied request metadata: **PASS**. The flow created a synthetic run, advanced it, read state, performed lookup, obtained a fail-closed answer validation, and purged the run.
- Codex native one-off host canary: **PASS**. Codex loaded only the fresh-wheel server through invocation-local config and completed one `get_trust_model` tool call. No user MCP configuration was changed.
- The first non-interactive Codex attempt was cancelled by host approval policy before the tool executed. A second read-only canary used the CLI's one-invocation approval bypass and succeeded. This was a host approval event, not a server or `_meta` failure.

## V0.6.1 matrix results

| Gate | Status | Evidence |
|---|---|---|
| RG-MCP-01 | PASS | `params._meta` and direct `arguments._meta` contract tests |
| RG-MCP-02 | PASS | all six high-level tools, fresh-wheel MCP SDK metadata canary |
| RG-MCP-03 | PASS | unknown business fields remain rejected |
| RG-JUD-01 | **BLOCKED** | no policy-approved 8-case real ordinary-court snapshot corpus in the public repo |
| RG-JUD-02 | PARTIAL | synthetic layout corpus false party-to-court promotions = 0; real corpus not run |
| RG-JUD-03 | PASS | partial parsing preserves an official non-eligible source |
| RG-IDR-01 | PASS | canonical `doc_id` and official-URL fallback promotion tests |
| RG-IDR-02 | PASS | canonical identifier mismatch blocks promotion |
| RG-PRIV-01 | PASS | 1,000- and 3,000-plus-character Chinese answer cases pass output privacy |
| RG-PRIV-02 | PASS | deterministic identifier/token redaction and confidential-content blocking |
| RG-GRD-01 | PASS | one reordered Chinese lexical/structural positive golden case |
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
- Core legal claims require evidence-ID bindings. Only bound evidence can affect stale, citation, role, and grounding decisions.
- The public implementation does not perform systematic counter-authority search. The coverage state remains false and final answers require an explicit limitation.

## Not executed or not satisfied

- Real V0.6.1 ordinary-court fixed corpus: **not executed / blocking** because no approved public-safe fixture path was provided and the repository policy forbids committing real corpus identifiers/content.
- Live canaries for a Supreme Court judgment, a district-court labor judgment, a real `事實及理由` page, and live TLR-to-official promotion: **not executed**. Synthetic integration tests do not replace these live checks.
- V0.6.2 operation leases/failure recovery and stable source-version identity: **deferred by specification**.

Until the real corpus governance conflict is resolved and the required live canaries are recorded, v0.6.1 must not be tagged, released, or described as public-preview ready.
