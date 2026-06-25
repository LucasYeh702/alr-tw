# Trust Chain

The trust chain separates retrieval candidates from final citations.

1. Official sources may be final citations.
2. Verified cache may be final only when official URL, hash, and verification time are present.
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
