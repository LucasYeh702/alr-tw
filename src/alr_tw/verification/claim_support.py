from __future__ import annotations

from enum import Enum


class ClaimSupportLevel(str, Enum):
    NOT_CHECKED = "not_checked"
    SOURCE_VERIFIED = "source_verified"
    QUOTE_PRESENT = "quote_present"
    HOLDING_CANDIDATE = "holding_candidate"
    CLAIM_SUPPORT_CANDIDATE = "claim_support_candidate"
    CLAIM_SUPPORTED = "claim_supported"
    HUMAN_REVIEW_REQUIRED = "human_review_required"

