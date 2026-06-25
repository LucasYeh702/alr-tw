from __future__ import annotations


def diff_status(expected_hash: str, actual_hash: str) -> str:
    return "match" if expected_hash == actual_hash else "mismatch"
