"""Central candidate identity resolution and verification ordering."""

from __future__ import annotations

from dataclasses import dataclass, field
from urllib.parse import parse_qs, unquote, urlsplit

from alr_tw.contracts.providers import ProviderCandidate
from alr_tw.providers.official.judgments import OfficialJudgmentProvider


@dataclass(frozen=True, slots=True)
class ResolvedJudgmentIdentity:
    lookup_identifier: str
    canonical_jid: str | None
    resolution_method: str
    candidate: ProviderCandidate | None = None
    merged_candidate_ids: tuple[str, ...] = field(default_factory=tuple)

    @property
    def dedupe_key(self) -> str:
        if self.canonical_jid:
            return f"jid:{self.canonical_jid}"
        if self.candidate is not None:
            return f"candidate:{self.candidate.provider_id}:{self.candidate.candidate_id}"
        return f"direct:{self.lookup_identifier}"


def direct_judgment_identity(identifier: str) -> ResolvedJudgmentIdentity:
    canonical = OfficialJudgmentProvider.normalize_jid(identifier)
    return ResolvedJudgmentIdentity(
        lookup_identifier=canonical or identifier,
        canonical_jid=canonical,
        resolution_method=("query_canonical_jid" if canonical else "query_formal_citation"),
    )


def resolve_judgment_candidate(
    candidate: ProviderCandidate,
) -> ResolvedJudgmentIdentity | None:
    identity = candidate.identity
    if identity is not None:
        canonical = OfficialJudgmentProvider.normalize_jid(identity.canonical_jid or "")
        if canonical:
            return _resolved(candidate, canonical, "typed_canonical_jid")

        canonical = _jid_from_identifier(identity.provider_document_id)
        if canonical:
            return _resolved(candidate, canonical, "provider_document_id")

        canonical = _jid_from_url(identity.official_url)
        if canonical:
            return _resolved(candidate, canonical, "typed_official_url")

    canonical = _jid_from_url(candidate.official_url)
    if canonical:
        return _resolved(candidate, canonical, "legacy_official_url")

    canonical = _jid_from_identifier(candidate.official_identifier)
    if canonical:
        return _resolved(candidate, canonical, "legacy_official_identifier")

    formal = (identity.formal_citation if identity is not None else None) or ""
    formal = formal.strip()
    if not formal:
        formal = str(candidate.official_identifier or candidate.title or "").strip()
    if formal and OfficialJudgmentProvider.normalize_formal_citation(formal) is not None:
        return ResolvedJudgmentIdentity(
            lookup_identifier=formal,
            canonical_jid=None,
            resolution_method="formal_citation",
            candidate=candidate,
            merged_candidate_ids=(candidate.candidate_id,),
        )

    legacy_doc_id = candidate.metadata.get("doc_id")
    canonical = _jid_from_identifier(str(legacy_doc_id or ""))
    if canonical:
        return _resolved(candidate, canonical, "legacy_metadata_doc_id")
    return None


def rank_and_dedupe_judgment_identities(
    identities: list[ResolvedJudgmentIdentity],
) -> list[ResolvedJudgmentIdentity]:
    ordered = sorted(identities, key=_sort_key)
    deduplicated: dict[str, ResolvedJudgmentIdentity] = {}
    merged_ids: dict[str, list[str]] = {}
    for item in ordered:
        key = item.dedupe_key
        merged_ids.setdefault(key, []).extend(item.merged_candidate_ids)
        if key not in deduplicated:
            deduplicated[key] = item
        elif deduplicated[key].candidate is None and item.candidate is not None:
            direct = deduplicated[key]
            deduplicated[key] = ResolvedJudgmentIdentity(
                lookup_identifier=direct.lookup_identifier,
                canonical_jid=direct.canonical_jid,
                resolution_method=item.resolution_method,
                candidate=item.candidate,
            )

    output: list[ResolvedJudgmentIdentity] = []
    for key, item in deduplicated.items():
        output.append(
            ResolvedJudgmentIdentity(
                lookup_identifier=item.lookup_identifier,
                canonical_jid=item.canonical_jid,
                resolution_method=item.resolution_method,
                candidate=item.candidate,
                merged_candidate_ids=tuple(dict.fromkeys(merged_ids[key])),
            )
        )
    return output


def _resolved(
    candidate: ProviderCandidate,
    canonical_jid: str,
    method: str,
) -> ResolvedJudgmentIdentity:
    return ResolvedJudgmentIdentity(
        lookup_identifier=canonical_jid,
        canonical_jid=canonical_jid,
        resolution_method=method,
        candidate=candidate,
        merged_candidate_ids=(candidate.candidate_id,),
    )


def _jid_from_identifier(value: str | None) -> str | None:
    if not value:
        return None
    return OfficialJudgmentProvider.normalize_jid(value) or _jid_from_url(value)


def _jid_from_url(value: str | None) -> str | None:
    if not value:
        return None
    canonical = OfficialJudgmentProvider.jid_from_identifier(value)
    if canonical:
        return canonical
    parsed = urlsplit(value.strip())
    if parsed.scheme != "https" or parsed.hostname != "judgment.judicial.gov.tw":
        return None
    for key in ("id", "jid", "j"):
        for raw in parse_qs(parsed.query).get(key, []):
            canonical = OfficialJudgmentProvider.normalize_jid(unquote(raw))
            if canonical:
                return canonical
    return None


def _sort_key(item: ResolvedJudgmentIdentity) -> tuple[int, int, float, str]:
    if item.candidate is None:
        provider_priority = 0
        rank = 0
        score = 0.0
        candidate_id = ""
    else:
        provider_priority = (
            1
            if item.candidate.provider_id == OfficialJudgmentProvider.provider_id
            and item.canonical_jid
            else 2
            if item.canonical_jid
            else 3
        )
        rank = item.candidate.candidate_rank or 2**31 - 1
        score = -(item.candidate.score or 0.0)
        candidate_id = item.candidate.candidate_id
    return provider_priority, rank, score, candidate_id
