---
title: "[RFC] Refine ResearchSufficiency & AnswerMode: Introduce Qualified Advisory to Prevent Total Draft Redaction under Bounded Scope"
labels: ["enhancement", "contracts", "civil-law"]
state: "draft"
author: "Third-Party Contributor / System Architect"
target_repo: "LucasYeh702/alr-tw"
---

# [RFC] Refine ResearchSufficiency & AnswerMode: Introduce Qualified Advisory to Prevent Total Draft Redaction under Bounded Scope

## 1. Summary
This RFC proposes refining the **`AnswerMode`** and **`ResearchSufficiency`** decision contracts in `alr-tw`.

Currently, the harness enforces a near-binary failure model: if counter-authority search coverage is bounded or inconclusive (`not_found_in_scope`), the engine frequently determines `research_sufficiency = insufficient` and sets `answer_mode = refusal_only`. Under the trust contract (`docs/TRUST_MODEL.md`), `refusal_only` and `blocked` mandate that the client must completely redact and purge the draft answer body (`answer: null`).

In Taiwanese civil-law practice, finding zero contrary judicial decisions within a bounded scope is standard. Refusing to output any answer whatsoever whenever counter-authority coverage is non-exhaustive undermines the real-world utility of the tool.

We propose distinguishing between:
1. **Fatal Authenticity Failures (Hard Failures)**: Fabricated JIDs, repealed/stale statutes without historical matching, or confirmed vacated/reversed rulings.
2. **Bounded Scope Limitations (Soft Incompleteness)**: Bounded counter-authority discovery where positive authorities are 100% verified and unreversed, but the search space did not exhaust all judicial levels.

For Soft Incompleteness, we propose introducing a **`qualified_advisory`** answer mode that permits displaying the verified answer body accompanied by a mandatory **Structural Risk Warning Envelope**.

---

## 2. Motivation & Problem Statement

### 2.1 The Civil-Law Reality of "Absence of Rebuttal"
In Taiwan civil and commercial litigation:
- A legal issue may be consistently supported by Supreme Court holdings without an active opposing school of thought.
- In `alr-tw`, counter-authority discovery is bounded (currently up to 4 lexical queries and up to 5 official checks).
- When these 4 queries return no negative hits, `alr-tw` correctly refuses to claim "consensus across the entire judiciary". However, it currently over-corrects by downgrading the entire research run to `refusal_only`.

### 2.2 The "Blocked Must Drop Draft" Penalty
Per `docs/TRUST_MODEL.md` (lines 88-91):
> *"Finalization does not authorize presenting answer body; only validated/qualified results of validate_legal_answer can be presented. refusal_only/blocked MUST remove the draft."*

This creates an all-or-nothing dilemma:
- A legal analyst who spent substantial tokens verifying 5 authentic Supreme Court judgments receives a blank refusal message, simply because the counter-authority obligation could not mathematically prove that no contrary judgment exists anywhere in 30 years of history.

---

## 3. Proposed Specification

### 3.1 Extended `AnswerMode` Enum
Update `alr_tw.contracts.finalization.AnswerMode`:

```python
class AnswerMode(str, Enum):
    ORDINARY = "ordinary"                  # Full consensus or authoritative snapshot receipt
    CONDITIONAL = "conditional"            # Authentic evidence with explicit temporal/procedural constraints
    QUALIFIED_ADVISORY = "qualified_advisory"  # [NEW] Authentic evidence verified, but counter-authority bounded
    REFUSAL_ONLY = "refusal_only"          # Fatal invalidity, unverified claims, or vacated precedents
```

### 3.2 Criteria for `QUALIFIED_ADVISORY`
A run is eligible for `QUALIFIED_ADVISORY` if and only if:
1. **Source Authenticity**: 100% of cited positive authorities are verified (`source_tier in {"official", "verified_cache"}`) with valid SHA-256 hashes.
2. **No Reversal**: No cited judgment is categorized as `CONFIRMED_REVERSAL` or vacated in its disposition.
3. **Temporal Validity**: Applicable statutes were verified active at `as_of_date`.
4. **Bounded Counter-Authority**: Counter-authority checks were conducted in good faith within the configured bounded scope, but no conflicting decisions were found.

### 3.3 The Structural Risk Warning Envelope
When `answer_mode == AnswerMode.QUALIFIED_ADVISORY`:
- The answer body is **NOT** blanked.
- The output JSON contract injects a mandatory, prominent disclaimer envelope:
```json
{
  "answer_mode": "qualified_advisory",
  "safe_to_present": true,
  "caveat_envelope": {
    "warning_code": "BOUNDED_COUNTER_AUTHORITY_UNEXHAUSTED",
    "notice_zh": "本法律分析所援引之主法條與判決均經司法院官方核實無誤，且無廢棄改判紀錄。惟反面見解檢索受限於指定檢索範圍，未能窮盡歷史各級法院裁判，不得據此逕行主張實務見解絕對一致。使用者應由具資格之律師進行最終個案事實涵攝與抗辯事由覆核。",
    "verified_authorities_count": 5,
    "counter_authority_scope": "bounded_lexical_4_queries"
  },
  "answer": "..."
}
```

---

## 4. Safety & Invariant Analysis
- **Zero Hallucination Guaranteed**: Fabricated citations, hallucinated case numbers, or fake statutory articles STILL trigger immediate, absolute `refusal_only` (hard failure).
- **No False Consensus Claims**: The contract explicitly forbids claiming universal consensus, satisfying ALR-TW's core civil-law doctrine.
- **Dramatically Improved Practical Utility**: Empowers professional lawyers to review verified supporting authorities and clear caveat statements, rather than receiving an unhelpful blank error.

---

## 5. Alternatives Considered
- **Keep pure binary refusal**: Leads users and downstream developers to write unofficial bypasses around `validate_legal_answer`, destroying the security boundaries ALR-TW was built to protect.
