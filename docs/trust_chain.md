# Trust Chain

> 適用版本：v1.0.0（套件 `1.0.0`）；功能與限制見 [1.0 說明](V1_RELEASE.md)。


The trust chain separates retrieval candidates from final citations.

1. Official sources are eligible only after server-owned identity, content, freshness, role, and claim-binding checks.
2. Verified cache requires trusted provenance and server-side content/hash, identity, and expiry verification. Merely supplying an official URL, hash, or timestamp does not establish trust.
3. TLR-like recall is candidate-only.
4. HF-like datasets are staging / audit / eval only.
5. Synthetic data is demo-only.

Unsupported authority fails closed.

The current synthetic demo also includes:

- stateful coverage report
- classifier shadow / overlay review boundary
- synthetic issue brief
- ranking evaluation
- trust gate summary
- source verification batch summary
- authority recall final-source filter
- exact lookup demo-only citations
