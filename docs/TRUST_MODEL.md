# ALR-TW Trust Model

## v0.6 evidence promotion

Final validation 只讀取該 run 在 server-side SQLite 中已連結、未到期且 `trust_status=evidence_eligible` 的 evidence。MCP caller 即使提交看似完整的 official URL、hash 或 verified time，也只能視為 caller-attested metadata，不能升格為正式證據。

官方 provider 取得的內容必須先形成 immutable snapshot，保存 official identifier、official URL、content hash、fetched/verified/expires timestamps 與 section role。TLR candidate、keyword-search hit、party argument、case fact、concurring opinion 與 dissenting opinion 都有獨立限制，不得因文字相似直接支持不同角色的 claim。

Final decisions 是 `validated`、`qualified`、`blocked`。`qualified` 只代表已驗證 evidence 支持 draft、但有明示召回限制；它不是降低來源門檻。`blocked` 不得包含 answer body。

ALR-TW separates source discovery from final citation authority.

## Source Tiers

| Tier | Role | Final citation |
|---|---|---|
| `official` | Official or official-grounded source | Yes |
| `verified_cache` | Cache with official URL, hash, and verified time | Yes, if complete |
| `staging` | Ingestion or audit candidate | No |
| `external_semantic_recall` | Candidate recall from an external semantic system | No |
| `synthetic` | Demo and test fixture | No |
| `unknown` | Missing or unsupported source tier | No |

Legacy Python contracts may expose metadata validation helpers, but the v0.6
MCP boundary does not trust caller-supplied metadata. Byte-level verification
must happen in a server-owned provider or governed resolver.

## Identifier-Backed Verified Cache (Opt-In)

By default, `verified_cache` requires an official URL, a content hash, and a
verification time. A deployer may enable the identifier-backed capability
(`ALR_TW_IDENTIFIER_BACKED_VERIFIED_CACHE`, default off) so a stable official
identifier such as a judgment JID substitutes for the URL. The substitution is
enforced, not declared: it applies to judgment-type records only, and a
resolver must map the identifier to a locally downloaded official original
record whose recomputed content hash matches the declared hash. Unresolved
identifiers, hash mismatches, and non-judgment materials fail closed with
explicit error codes.

Scope caveat: the server-side enforcement statement applies to the MCP surface.
At the Python library level, `identifier_resolution` is part of the
adapter/verifier trust boundary. It must be set only by the deployer's resolver
layer, such as `resolve_identifier_citation`; setting it by hand is vouching for
the record.

## Citation Use

- `allow_final`: may satisfy final citation requirement.
- `allow_candidate_only`: may help discovery but cannot support final answer.
- `demo_only`: synthetic fixture only.
- `reject`: cannot be used.

## Citation Eligibility

`citation_eligibility` is separate from claim support:

- `final_eligible`: source tier and metadata can support final-citation eligibility.
- `candidate_only`: source may help discovery only.
- `demo_only`: source is synthetic demonstration data only.
- `rejected`: source tier or metadata failed the policy.
- `missing`: citation was not found.

`support: not_checked` means the public harness has not verified that a source
actually entails a legal claim. Production systems should add a separate
claim-support or legal-effect layer before presenting legal analysis.

## Fail-Closed Rules

ALR-TW refuses when there is no final citation, a rejected or unverifiable
source, or low required coverage. It may return `human_review_required` only
when final citation eligibility exists and the remaining blocker is unchecked
claim support. Non-answer traces must keep `answer` as `null`.
