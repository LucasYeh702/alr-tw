"""Central candidate identity resolution and verification ordering."""

from __future__ import annotations

import re
import unicodedata
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

        partial = _partial_jid_from_identifier(identity.provider_document_id)
        if partial:
            return _resolved_partial(candidate, partial, "provider_partial_jid")

        canonical = _jid_from_url(identity.official_url)
        if canonical:
            return _resolved(candidate, canonical, "typed_official_url")

        partial = _partial_jid_from_identifier(identity.official_url)
        if partial:
            return _resolved_partial(candidate, partial, "typed_partial_official_url")

    canonical = _jid_from_url(candidate.official_url)
    if canonical:
        return _resolved(candidate, canonical, "legacy_official_url")

    partial = _partial_jid_from_identifier(candidate.official_url)
    if partial:
        return _resolved_partial(candidate, partial, "legacy_partial_official_url")

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
    partial = _partial_jid_from_identifier(str(legacy_doc_id or ""))
    if partial:
        return _resolved_partial(candidate, partial, "legacy_metadata_partial_jid")
    return None


def rank_and_dedupe_judgment_identities(
    identities: list[ResolvedJudgmentIdentity],
    *,
    query: str = "",
) -> list[ResolvedJudgmentIdentity]:
    ordered = sorted(identities, key=lambda item: _sort_key(item, query=query))
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


def _resolved_partial(
    candidate: ProviderCandidate,
    partial_jid: str,
    method: str,
) -> ResolvedJudgmentIdentity:
    return ResolvedJudgmentIdentity(
        lookup_identifier=partial_jid,
        canonical_jid=None,
        resolution_method=method,
        candidate=candidate,
        merged_candidate_ids=(candidate.candidate_id,),
    )


def _jid_from_identifier(value: str | None) -> str | None:
    if not value:
        return None
    return OfficialJudgmentProvider.normalize_jid(value) or _jid_from_url(value)


def _partial_jid_from_identifier(value: str | None) -> str | None:
    if not value:
        return None
    return OfficialJudgmentProvider.partial_jid_from_identifier(value)


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


def _sort_key(
    item: ResolvedJudgmentIdentity,
    *,
    query: str,
) -> tuple[int, float, int, float, str]:
    if item.candidate is None:
        provider_priority = 0
        relevance = 0.0
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
        relevance = _query_relevance(item.candidate, query)
        rank = item.candidate.candidate_rank or 2**31 - 1
        score = -(item.candidate.score or 0.0)
        candidate_id = item.candidate.candidate_id
    return provider_priority, -relevance, rank, score, candidate_id


def _query_relevance(candidate: ProviderCandidate, query: str) -> float:
    """Cheap local reranker; candidates remain untrusted until official verification."""

    normalized_query = _compact_text(query[:512])
    if len(normalized_query) < 2:
        return 0.0
    fields = [candidate.title or "", candidate.excerpt or ""]
    fields.extend(
        str(candidate.metadata.get(key) or "")
        for key in (
            "citation_text",
            "case_cause",
            "court",
            "court_name",
            "case_type",
            "case_category",
        )
    )
    candidate_text = _compact_text(" ".join(fields)[:8192])
    if not candidate_text:
        return 0.0

    query_ngrams = _ngrams(normalized_query)
    candidate_ngrams = _ngrams(candidate_text)
    overlap = query_ngrams & candidate_ngrams
    score = float(sum(len(token) ** 2 for token in overlap))

    civil_cues = ("勞動", "勞工", "雇主", "解僱", "資遣", "契約", "民法", "損害賠償")
    criminal_cues = ("犯罪", "刑法", "刑事", "有罪", "無罪", "詐欺", "竊盜", "量刑")
    query_is_civil = any(token in normalized_query for token in civil_cues)
    query_is_criminal = any(token in normalized_query for token in criminal_cues)
    if query_is_civil and not query_is_criminal and "刑事" in candidate_text:
        score -= 10_000.0
    elif query_is_criminal and not query_is_civil and "民事" in candidate_text:
        score -= 10_000.0
    return score


def _compact_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).lower()
    return re.sub(r"[^0-9a-z\u3400-\u9fff]+", "", normalized)


def _ngrams(value: str) -> set[str]:
    return {
        value[index : index + size]
        for size in (2, 3, 4)
        for index in range(max(0, len(value) - size + 1))
    }
