from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any, Mapping

from alr_tw.contracts.providers import ProviderErrorCode, ProviderResultStatus
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
                    "citation_url": "https://judgment.judicial.gov.tw/synthetic",
                    "result_token": "temporary-result-handle",
                }
            ]
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
