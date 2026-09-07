from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any, Mapping

from alr_tw.contracts.providers import ProviderErrorCode, ProviderResultStatus
from alr_tw.contracts.public_law import (
    PublicLawMaterialType,
    PublicLawResultStatus,
    PublicLawSearchRequest,
    PublicLawSourceRole,
    PublicLawValidationDecision,
    validate_public_law_result,
)
from alr_tw.contracts.research import PrivacyStatus
from alr_tw.contracts.sources import SourceTier, TrustStatus
from alr_tw.providers.tlr import TlrSemanticRecallProvider, screen_external_query
from alr_tw.providers.tlr.provider import TlrHttpResponse


class FixtureTlrTransport:
    def __init__(self, responses: list[TlrHttpResponse]):
        self.responses = responses
        self.posts: list[tuple[str, Mapping[str, Any], Mapping[str, str]]] = []

    async def get_json(
        self,
        url: str,
        *,
        headers: Mapping[str, str],
        timeout: float,
        max_bytes: int,
    ) -> TlrHttpResponse:
        del url, headers, timeout, max_bytes
        return TlrHttpResponse(200, {"openapi": "3.1.0"})

    async def post_json(
        self,
        url: str,
        body: Mapping[str, Any],
        *,
        headers: Mapping[str, str],
        timeout: float,
        max_bytes: int,
    ) -> TlrHttpResponse:
        assert timeout > 0 and max_bytes > 0
        self.posts.append((url, body, headers))
        return self.responses.pop(0)


def _search_response() -> TlrHttpResponse:
    return TlrHttpResponse(
        200,
        {
            "results": [
                {
                    "rank": 1,
                    "doc_id": "synthetic-doc-1",
                    "citation_text": "臺灣示範法院130年度測字第1號",
                    "court_name": "臺灣示範法院",
                    "jdate": "20410102",
                    "case_category": "合成",
                    "snippet": "結構化候選摘要，不是法院論理。",
                    "hit_excerpt": "查詢詞命中的候選段落，不是正式證據。",
                    "citation_url": "https://judgment.judicial.gov.tw/synthetic",
                    "result_token": "temporary-result-handle",
                }
            ]
        },
    )


def _administrative_search_response() -> TlrHttpResponse:
    return TlrHttpResponse(
        200,
        {
            "candidate_count": 1,
            "rejected": {"source_hash_mismatch": 2},
            "notes": ["候選召回不代表現行有效。"],
            "results": [
                {
                    "citation": "示範部會測字第1300001號函",
                    "canonical_id": "demo-agency:1300001",
                    "serial_no": "測字第1300001號函",
                    "authority": "示範部會",
                    "title": "測試行政函釋",
                    "issue_date": "2041-01-02",
                    "source_kind": "administrative_interpretation",
                    "status": "active_verified",
                    "score": 0.82,
                    "excerpt": "命中片段只能用於判斷是否值得官方回查。",
                    "fulltext_chars": 8800,
                }
            ],
        },
    )


def _public_law_request(*, max_results: int = 5) -> PublicLawSearchRequest:
    return PublicLawSearchRequest(
        query_id="query-tlr-public-law-1",
        query="行政處分作成前陳述意見之程序",
        material_types=[PublicLawMaterialType.ADMINISTRATIVE_INTERPRETATION],
        bounded_scope="tlr-administrative-interpretation-candidates",
        max_results=max_results,
    )


def _paged_fulltext_response(
    *,
    offset: int,
    text: str,
    total: int,
    truncated: bool,
) -> TlrHttpResponse:
    header = (
        "引用連結: [最高示範法院130年度測上字第1號](https://example.test/demo)\n"
        "引用字號: 最高示範法院130年度測上字第1號\n\n"
    )
    return TlrHttpResponse(
        200,
        {
            "doc_id": "DEMO,130,測上,1,20990102,1",
            "citation_text": "最高示範法院130年度測上字第1號",
            "text_excerpt": header + text,
            "excerpt_offset": offset,
            "fulltext_total_chars": total,
            "fulltext_truncated": truncated,
        },
    )


def _fulltext_response() -> TlrHttpResponse:
    return TlrHttpResponse(
        200,
        {
            "doc_id": "DEMO,130,測上,1,20990102,1",
            "citation_text": "最高示範法院130年度測上字第1號",
            "text_excerpt": "TLR excerpt must not become ALR-TW evidence.",
            "case_history": {
                "upper": [
                    {
                        "citation_text": "最高示範法院131年度測上字第2號",
                        "doc_id": "DEMO,131,測上,2,21000102,1",
                        "doc_type": "判決",
                        "jdate": "2100-01-02",
                        "main_flag": "主文含「廢棄」",
                    }
                ],
                "lower": [
                    {
                        "citation_text": "臺灣示範地方法院129年度測字第3號",
                        "doc_id": "DEMO,129,測,3,20980102,1",
                        "doc_type": "判決",
                        "jdate": "2098-01-02",
                        "main_flag": None,
                    }
                ],
                "note": "Database-recorded only; absence does not establish finality.",
            },
        },
    )


def test_privacy_screen_redacts_pii_and_blocks_strategy() -> None:
    redacted = screen_external_query("加班費請求，聯絡電話 0912-345-678 的時效規定")
    sensitive = screen_external_query("請分析我方訴訟策略與證據弱點")
    uncertain = screen_external_query("我方當事人和對方被告就未具名個案發生爭議")

    assert redacted.status == PrivacyStatus.REDACTED_SAFE
    assert redacted.allowed and "0912" not in (redacted.query_to_send or "")
    assert sensitive.status == PrivacyStatus.SENSITIVE and not sensitive.allowed
    assert uncertain.status == PrivacyStatus.UNCERTAIN and not uncertain.allowed


def test_tlr_search_returns_candidate_only_source() -> None:
    transport = FixtureTlrTransport([_search_response()])
    provider = TlrSemanticRecallProvider(transport=transport)

    result, sources, privacy = asyncio.run(
        provider.search("勞動契約加班費舉證責任", now=datetime(2041, 1, 3, tzinfo=UTC))
    )

    assert privacy.status == PrivacyStatus.SAFE
    assert result.status == ProviderResultStatus.FOUND
    assert result.evidence_ids == []
    assert len(sources) == 1
    assert sources[0].source_tier == SourceTier.EXTERNAL_SEMANTIC_RECALL
    assert sources[0].trust_status == TrustStatus.EXTERNAL_CANDIDATE
    assert "TLR_CANDIDATE_ONLY" in sources[0].warnings
    assert result.candidates[0].metadata["doc_id"] == "synthetic-doc-1"
    assert result.candidates[0].identity is not None
    assert result.candidates[0].identity.provider_document_id == "synthetic-doc-1"
    assert result.candidates[0].candidate_rank == 1
    assert result.candidates[0].excerpt == "查詢詞命中的候選段落，不是正式證據。"
    assert result.candidates[0].metadata["structural_snippet"] == (
        "結構化候選摘要，不是法院論理。"
    )
    assert result.candidates[0].metadata["hit_excerpt_truncated"] is False
    assert "TLR_HIT_EXCERPT_IS_NOT_EVIDENCE" in sources[0].warnings


def test_tlr_privacy_block_makes_no_network_call() -> None:
    transport = FixtureTlrTransport([_search_response()])
    provider = TlrSemanticRecallProvider(transport=transport)

    result, sources, privacy = asyncio.run(provider.search("這是公司內部代號與談判底線"))

    assert privacy.status == PrivacyStatus.SENSITIVE
    assert result.error_code == ProviderErrorCode.PRIVACY_EXTERNAL_QUERY_BLOCKED
    assert sources == [] and transport.posts == []


def test_tlr_unavailable_is_retry_bounded_and_not_not_found() -> None:
    transport = FixtureTlrTransport(
        [TlrHttpResponse(503, {"detail": "busy"}), TlrHttpResponse(503, {"detail": "busy"})]
    )
    provider = TlrSemanticRecallProvider(transport=transport, max_retries=1)

    result, sources, _ = asyncio.run(provider.search("侵權行為損害賠償"))

    assert len(transport.posts) == 2
    assert result.status == ProviderResultStatus.ERROR
    assert result.error_code == ProviderErrorCode.TLR_UNAVAILABLE
    assert sources == []


def test_tlr_schema_change_fails_closed() -> None:
    provider = TlrSemanticRecallProvider(
        transport=FixtureTlrTransport([TlrHttpResponse(200, {"items": []})])
    )

    result, sources, _ = asyncio.run(provider.search("行政處分撤銷"))

    assert result.error_code == ProviderErrorCode.EXTERNAL_PROVIDER_SCHEMA_CHANGED
    assert sources == []


def test_tlr_response_cannot_exceed_requested_top_k() -> None:
    base = _search_response().payload["results"][0]
    response = TlrHttpResponse(
        200,
        {
            "results": [
                {
                    **base,
                    "rank": index,
                    "doc_id": f"synthetic-doc-{index}",
                }
                for index in range(1, 7)
            ]
        },
    )
    provider = TlrSemanticRecallProvider(transport=FixtureTlrTransport([response]))

    result, sources, _ = asyncio.run(provider.search("行政處分撤銷", top_k=5))

    assert result.status is ProviderResultStatus.ERROR
    assert result.error_code is ProviderErrorCode.EXTERNAL_PROVIDER_SCHEMA_CHANGED
    assert result.message == "TLR_SEARCH_RESULT_LIMIT_EXCEEDED"
    assert sources == []


def test_tlr_administrative_response_cannot_exceed_requested_top_k() -> None:
    base = _administrative_search_response().payload["results"][0]
    response = TlrHttpResponse(
        200,
        {
            "candidate_count": 6,
            "rejected": {},
            "results": [
                {
                    **base,
                    "canonical_id": f"demo-agency:{index}",
                    "serial_no": f"測字第{index}號函",
                    "citation": f"示範部會測字第{index}號函",
                }
                for index in range(1, 7)
            ],
        },
    )
    provider = TlrSemanticRecallProvider(transport=FixtureTlrTransport([response]))

    result, _ = asyncio.run(
        provider.search_administrative_interpretations(_public_law_request(max_results=5))
    )

    assert result.status is PublicLawResultStatus.RETRY_REQUIRED
    assert result.reason_codes == ["TLR_PUBLIC_LAW_SCHEMA_CHANGED"]
    assert result.metadata["provider_error"] == "TLR_PUBLIC_LAW_RESULT_LIMIT_EXCEEDED"
    assert result.candidates == []


def test_tlr_administrative_interpretation_recall_is_candidate_only() -> None:
    transport = FixtureTlrTransport([_administrative_search_response()])
    provider = TlrSemanticRecallProvider(transport=transport)
    capabilities = provider.public_law_capabilities()

    assert capabilities.semantic_recall is True
    assert capabilities.external_query_transfer is True
    assert capabilities.server_verification is False

    result, privacy = asyncio.run(
        provider.search_administrative_interpretations(
            _public_law_request(),
            authority="示範部會",
        )
    )

    assert privacy.status is PrivacyStatus.SAFE
    assert result.status is PublicLawResultStatus.PARTIAL
    assert result.coverage_complete is False and result.absence_claim_allowed is False
    assert result.sources == [] and result.server_metadata is None
    assert result.semantic_conclusion_performed is False
    assert result.reason_codes[:2] == [
        "PUBLIC_LAW_CANDIDATES_ONLY",
        "PUBLIC_LAW_COVERAGE_PARTIAL",
    ]
    assert "TLR_PUBLIC_LAW_PROVIDER_REJECTED_CANDIDATES" in result.reason_codes
    candidate = result.candidates[0]
    assert candidate.material_type is PublicLawMaterialType.ADMINISTRATIVE_INTERPRETATION
    assert candidate.source_role is PublicLawSourceRole.INTERPRETIVE_GUIDANCE
    assert candidate.excerpt == "命中片段只能用於判斷是否值得官方回查。"
    assert candidate.metadata["fulltext_total_chars"] == 8800
    assert candidate.metadata["hit_excerpt_truncated"] is True
    assert candidate.metadata["evidence_eligible"] is False
    assert transport.posts[0][0].endswith("/v1/legal_references/search")
    assert transport.posts[0][1]["source_kind"] == "administrative_interpretation"
    assert transport.posts[0][1]["authority"] == "示範部會"

    validation = validate_public_law_result(result, server_metadata=None)
    assert validation.decision is PublicLawValidationDecision.BLOCKED
    assert validation.eligible_source_ids == []


def test_tlr_administrative_recall_empty_is_not_scoped_absence() -> None:
    provider = TlrSemanticRecallProvider(
        transport=FixtureTlrTransport(
            [
                TlrHttpResponse(
                    200,
                    {
                        "candidate_count": 0,
                        "rejected": {},
                        "notes": ["查無不代表不存在。"],
                        "results": [],
                    },
                )
            ]
        )
    )

    result, _ = asyncio.run(
        provider.search_administrative_interpretations(_public_law_request())
    )

    assert result.status is PublicLawResultStatus.PARTIAL
    assert result.candidates == [] and result.absence_claim_allowed is False
    assert "TLR_PUBLIC_LAW_NOT_FOUND_IS_BOUNDED_ONLY" in result.reason_codes


def test_tlr_administrative_recall_privacy_block_makes_no_network_call() -> None:
    transport = FixtureTlrTransport([_administrative_search_response()])
    provider = TlrSemanticRecallProvider(transport=transport)
    request = _public_law_request().model_copy(
        update={"query": "我方公司的訴訟策略與證據弱點"}
    )

    result, privacy = asyncio.run(
        provider.search_administrative_interpretations(request)
    )

    assert privacy.status is PrivacyStatus.SENSITIVE
    assert result.status is PublicLawResultStatus.BLOCKED
    assert result.reason_codes == ["PRIVACY_EXTERNAL_QUERY_BLOCKED"]
    assert transport.posts == []


def test_tlr_candidate_fulltext_paginates_without_creating_evidence() -> None:
    transport = FixtureTlrTransport(
        [
            _paged_fulltext_response(offset=0, text="甲" * 4, total=7, truncated=True),
            _paged_fulltext_response(offset=4, text="乙" * 3, total=7, truncated=False),
        ]
    )
    provider = TlrSemanticRecallProvider(transport=transport)

    result, record = asyncio.run(
        provider.read_candidate_fulltext(
            "DEMO,130,測上,1,20990102,1",
            "temporary-result-handle",
        )
    )

    assert result.status is ProviderResultStatus.FOUND
    assert result.source_ids == [] and result.evidence_ids == []
    assert record is not None
    assert record.text == "甲" * 4 + "乙" * 3
    assert record.returned_chars == record.fulltext_total_chars == 7
    assert record.fulltext_truncated is False
    assert record.provider_content_complete is True
    assert record.evidence_eligible is False
    assert record.official_verification_required is True
    assert record.coverage_complete is False
    assert record.page_count == 2
    assert transport.posts[0][1].get("excerpt_offset") is None
    assert transport.posts[1][1]["excerpt_offset"] == 4


def test_tlr_candidate_fulltext_page_cap_exposes_resume_offset() -> None:
    provider = TlrSemanticRecallProvider(
        transport=FixtureTlrTransport(
            [_paged_fulltext_response(offset=0, text="甲" * 4, total=7, truncated=True)]
        )
    )

    result, record = asyncio.run(
        provider.read_candidate_fulltext(
            "DEMO,130,測上,1,20990102,1",
            "temporary-result-handle",
            max_pages=1,
        )
    )

    assert result.status is ProviderResultStatus.PARTIAL
    assert record is not None and record.fulltext_truncated is True
    assert record.next_excerpt_offset == 4
    assert record.provider_content_complete is False


def test_tlr_candidate_fulltext_inconsistent_completion_fails_closed() -> None:
    provider = TlrSemanticRecallProvider(
        transport=FixtureTlrTransport(
            [_paged_fulltext_response(offset=0, text="甲" * 4, total=7, truncated=False)]
        )
    )

    result, record = asyncio.run(
        provider.read_candidate_fulltext(
            "DEMO,130,測上,1,20990102,1",
            "temporary-result-handle",
        )
    )

    assert result.status is ProviderResultStatus.ERROR
    assert result.error_code is ProviderErrorCode.EXTERNAL_PROVIDER_SCHEMA_CHANGED
    assert result.message == "TLR_FULLTEXT_COMPLETION_LENGTH_MISMATCH"
    assert record is None and result.evidence_ids == []


def test_tlr_case_history_projects_metadata_without_fulltext_evidence() -> None:
    transport = FixtureTlrTransport([_fulltext_response()])
    provider = TlrSemanticRecallProvider(transport=transport)

    result, history = asyncio.run(
        provider.case_history(
            "DEMO,130,測上,1,20990102,1",
            "temporary-result-handle",
        )
    )

    assert result.status == ProviderResultStatus.FOUND
    assert result.coverage_complete is False
    assert result.source_ids == [] and result.evidence_ids == []
    assert history is not None
    assert history.establishes_finality is False
    assert history.semantic_opinion_comparison_performed is False
    assert [item.direction for item in history.entries] == ["upper", "lower"]
    assert all(item.evidence_eligible is False for item in history.entries)
    assert history.entries[0].vacated_marker is True
    assert "text_excerpt" not in history.model_dump()
    assert transport.posts[0][0].endswith("/v1/fulltext")


def test_tlr_case_history_missing_field_is_partial_not_finality() -> None:
    provider = TlrSemanticRecallProvider(
        transport=FixtureTlrTransport(
            [
                TlrHttpResponse(
                    200,
                    {
                        "doc_id": "DEMO,130,測上,1,20990102,1",
                        "citation_text": "最高示範法院130年度測上字第1號",
                    },
                )
            ]
        )
    )

    result, history = asyncio.run(
        provider.case_history(
            "DEMO,130,測上,1,20990102,1",
            "temporary-result-handle",
        )
    )

    assert result.status == ProviderResultStatus.PARTIAL
    assert history is not None and history.history_present is False
    assert history.entries == [] and history.establishes_finality is False


def test_tlr_case_history_stale_token_is_distinct_and_retryable_by_caller() -> None:
    provider = TlrSemanticRecallProvider(
        transport=FixtureTlrTransport(
            [
                TlrHttpResponse(
                    400,
                    {"detail": "result_token_invalid_or_expired; rerun search once"},
                )
            ]
        )
    )

    result, history = asyncio.run(
        provider.case_history(
            "DEMO,130,測上,1,20990102,1",
            "stale-result-handle",
        )
    )

    assert result.error_code == ProviderErrorCode.TLR_RESULT_TOKEN_INVALID_OR_EXPIRED
    assert history is None


def test_tlr_case_history_identity_mismatch_fails_closed() -> None:
    response = _fulltext_response()
    provider = TlrSemanticRecallProvider(transport=FixtureTlrTransport([response]))

    result, history = asyncio.run(
        provider.case_history(
            "DEMO,130,測上,999,20990102,1",
            "temporary-result-handle",
        )
    )

    assert result.error_code == ProviderErrorCode.EXTERNAL_PROVIDER_SCHEMA_CHANGED
    assert result.message == "TLR_FULLTEXT_IDENTITY_MISMATCH"
    assert history is None
