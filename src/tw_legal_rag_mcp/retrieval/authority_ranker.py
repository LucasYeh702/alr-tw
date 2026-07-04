"""Demo authority scores, not production ranking configuration.

The tier scores are illustrative public defaults for tests and examples. They
do not represent tuned production ranking weights.
"""

from __future__ import annotations


AUTHORITY_WEIGHT = {
    "official": 100,
    "verified_cache": 90,
    "synthetic": 10,
    "staging": 5,
    "external_semantic_recall": 5,
}


def authority_score(source_tier: str) -> int:
    return AUTHORITY_WEIGHT.get(source_tier, 0)
