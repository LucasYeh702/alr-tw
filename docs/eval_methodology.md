# Evaluation Methodology

> 適用版本：v1.0.0（套件 `1.0.0`）；功能與限制見 [1.0 說明](V1_RELEASE.md)。


This v1.0.0 repository includes a small synthetic test set only. Synthetic
records are contract fixtures and cannot support a legal answer.

The evaluation checks:

- source tier classification
- citation validator status
- candidate-only rejection for final citations
- non-boolean coverage flags
- workflow completion versus research sufficiency and answer mode
- bounded Coverage v2, snapshot receipts, and structured refusal
- privacy masking before external recall
- bounded counter-authority candidate discovery and official verification

It intentionally does not include complete legal corpora, production eval holdouts, or real user logs.

## External ChronoLex-TW adapter

The repository also provides a version-pinned adapter for the external
`lianghsun/chronolex-tw` benchmark. The dataset is not bundled or fetched at runtime.
The adapter keeps masked agent inputs separate from evaluator gold fields and requires
accepted ALR-TW historical-source plus applicability validation before scoring a law
version. See [CHRONOLEX_TW_ADAPTER.md](CHRONOLEX_TW_ADAPTER.md).
