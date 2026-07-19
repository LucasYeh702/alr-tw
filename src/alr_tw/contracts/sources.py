"""Source provenance and server-owned evidence contracts."""

from __future__ import annotations

import hashlib
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class SourceTier(str, Enum):
    OFFICIAL = "official"
    VERIFIED_CACHE = "verified_cache"
    STAGING = "staging"
    EXTERNAL_SEMANTIC_RECALL = "external_semantic_recall"
    SYNTHETIC = "synthetic"
    UNKNOWN = "unknown"


class TrustStatus(str, Enum):
    EXTERNAL_CANDIDATE = "external_candidate"
    OFFICIAL_FETCHED = "official_fetched"
    OFFICIAL_VERIFIED = "official_verified"
    EVIDENCE_ELIGIBLE = "evidence_eligible"
    STALE = "stale"
    VERIFICATION_FAILED = "verification_failed"
    PURGED = "purged"


class MaterialType(str, Enum):
    LAW = "law"
    JUDGMENT = "judgment"
    CONSTITUTIONAL = "constitutional"


class EvidenceSectionType(str, Enum):
    LAW_TEXT = "law_text"
    HOLDING = "holding"
    DISPOSITION = "disposition"
    COURT_REASONING = "court_reasoning"
    PARTY_ARGUMENT = "party_argument"
    FACTS = "facts"
    CONCURRING_OPINION = "concurring_opinion"
    DISSENTING_OPINION = "dissenting_opinion"
    OTHER = "other"


def _is_aware(value: datetime) -> bool:
    return value.tzinfo is not None and value.utcoffset() is not None


class SourceRecord(BaseModel):
    """Immutable content snapshot produced and verified by the server."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: str = "alr-tw.source-record/v2"
    source_id: str = Field(min_length=1)
    source_key: str = Field(min_length=1)
    source_version_id: str = Field(min_length=1)
    material_type: MaterialType
    provider_id: str = Field(min_length=1)
    source_tier: SourceTier
    trust_status: TrustStatus
    official_identifier: str | None = None
    official_url: str | None = None
    citation: str = Field(min_length=1)
    title: str | None = None
    fetched_at: datetime
    verified_at: datetime | None = None
    expires_at: datetime
    content_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    normalized_content_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    normalized_text: str = Field(min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_timestamps_and_trust(self) -> SourceRecord:
        timestamps = [self.fetched_at, self.expires_at]
        if self.verified_at is not None:
            timestamps.append(self.verified_at)
        if any(not _is_aware(value) for value in timestamps):
            raise ValueError("source timestamps must be timezone-aware")
        if self.expires_at <= self.fetched_at:
            raise ValueError("expires_at must be later than fetched_at")
        if self.trust_status in {
            TrustStatus.OFFICIAL_VERIFIED,
            TrustStatus.EVIDENCE_ELIGIBLE,
        }:
            if self.verified_at is None:
                raise ValueError("verified sources require verified_at")
            if not (self.official_identifier or self.official_url):
                raise ValueError("verified sources require an official identifier or URL")
        if self.source_tier == SourceTier.EXTERNAL_SEMANTIC_RECALL and self.trust_status not in {
            TrustStatus.EXTERNAL_CANDIDATE,
            TrustStatus.STALE,
            TrustStatus.VERIFICATION_FAILED,
        }:
            raise ValueError("external semantic recall cannot be evidence eligible")
        return self


class EvidenceSpan(BaseModel):
    """Exact server-owned source span used to support an answer claim."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: str = "alr-tw.evidence-span/v1"
    evidence_id: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    section_id: str = Field(min_length=1)
    section_type: EvidenceSectionType
    exact_text: str = Field(min_length=1)
    text_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    start_offset: int | None = Field(default=None, ge=0)
    end_offset: int | None = Field(default=None, ge=0)
    eligible_for_claim_support: bool

    @model_validator(mode="after")
    def validate_offsets_and_hash(self) -> EvidenceSpan:
        if (self.start_offset is None) != (self.end_offset is None):
            raise ValueError("start_offset and end_offset must be provided together")
        if (
            self.start_offset is not None
            and self.end_offset is not None
            and self.end_offset < self.start_offset
        ):
            raise ValueError("end_offset must not precede start_offset")
        if not self.verify_text(self.exact_text):
            raise ValueError("text_hash does not match exact_text")
        return self

    @staticmethod
    def hash_text(text: str) -> str:
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        return f"sha256:{digest}"

    @classmethod
    def from_exact_text(
        cls,
        *,
        evidence_id: str,
        source_id: str,
        section_id: str,
        section_type: EvidenceSectionType | str,
        exact_text: str,
        eligible_for_claim_support: bool,
        start_offset: int | None = None,
        end_offset: int | None = None,
    ) -> EvidenceSpan:
        return cls(
            evidence_id=evidence_id,
            source_id=source_id,
            section_id=section_id,
            section_type=EvidenceSectionType(section_type),
            exact_text=exact_text,
            text_hash=cls.hash_text(exact_text),
            start_offset=start_offset,
            end_offset=end_offset,
            eligible_for_claim_support=eligible_for_claim_support,
        )

    def verify_text(self, text: str) -> bool:
        return self.text_hash == self.hash_text(text)
