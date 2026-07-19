from __future__ import annotations

import asyncio
import io
import json
import zipfile
from datetime import UTC, datetime

import pytest

from alr_tw.contracts.providers import ProviderErrorCode, ProviderResultStatus
from alr_tw.contracts.sources import SourceTier, TrustStatus
from alr_tw.providers.official.http import HttpResponse
from alr_tw.providers.official.laws import LAW_DATA_URL, OfficialLawProvider


def _archive(*, abandoned: bool = False) -> bytes:
    document = {
        "UpdateDate": "2099/1/1",
        "Laws": [
            {
                "LawName": "示範程序法",
                "LawURL": (
                    "https://law.moj.gov.tw/LawClass/LawAll.aspx?pcode=DEMO0001"
                ),
                "LawModifiedDate": "20990101",
                "LawEffectiveDate": "20990101",
                "LawAbandonNote": "已廢止" if abandoned else "",
                "LawArticles": [
                    {
                        "ArticleType": "A",
                        "ArticleNo": "第 12-1 條",
                        "ArticleContent": "合成測試資料不得作為真實法律意見。",
                    }
                ],
            }
        ],
    }
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("ChLaw.json", json.dumps(document, ensure_ascii=False))
    return buffer.getvalue()


class FixtureTransport:
    def __init__(self, payload: bytes, status_code: int = 200):
        self.payload = payload
        self.status_code = status_code
        self.calls: list[str] = []

    async def get(self, url: str, *, timeout: float, max_bytes: int) -> HttpResponse:
        assert timeout > 0
        assert max_bytes >= len(self.payload)
        self.calls.append(url)
        return HttpResponse(self.status_code, self.payload, {}, url)


class ArchiveThenPageTransport:
    def __init__(self, page: str):
        self.page = page
        self.calls = 0

    async def get(self, url: str, *, timeout: float, max_bytes: int) -> HttpResponse:
        del timeout, max_bytes
        self.calls += 1
        payload = _archive() if self.calls == 1 else self.page.encode()
        return HttpResponse(200, payload, {}, url)


def test_official_law_exact_lookup_promotes_server_snapshot() -> None:
    transport = FixtureTransport(_archive())
    provider = OfficialLawProvider(transport, verify_webpage=False)

    result, source, evidence = asyncio.run(
        provider.exact_lookup(
            "示範程序法",
            "第 012 之 1 條",
            now=datetime(2099, 1, 2, tzinfo=UTC),
        )
    )

    assert transport.calls == [LAW_DATA_URL]
    assert result.status == ProviderResultStatus.FOUND
    assert source is not None and evidence is not None
    assert source.source_tier == SourceTier.OFFICIAL
    assert source.trust_status == TrustStatus.EVIDENCE_ELIGIBLE
    assert source.official_identifier == "DEMO0001:12-1"
    assert evidence.eligible_for_claim_support
    assert evidence.verify_text(source.normalized_text)


def test_official_law_search_and_not_found_are_distinct_from_failure() -> None:
    provider = OfficialLawProvider(FixtureTransport(_archive()), verify_webpage=False)

    search = asyncio.run(provider.search("合成測試"))
    missing, source, evidence = asyncio.run(provider.exact_lookup("不存在法", "1"))

    assert search.status == ProviderResultStatus.FOUND
    assert search.metadata["matches"][0]["law_name"] == "示範程序法"
    assert missing.status == ProviderResultStatus.NOT_FOUND
    assert missing.error_code == ProviderErrorCode.OFFICIAL_SOURCE_NOT_FOUND
    assert source is None and evidence is None


def test_official_catalog_resolves_citation_inside_natural_question() -> None:
    provider = OfficialLawProvider(FixtureTransport(_archive()), verify_webpage=False)

    citations = asyncio.run(
        provider.resolve_citations("請問依示範程序法第12之1條，應如何處理？")
    )

    assert citations == [("示範程序法", "12-1")]


def test_repealed_law_is_not_eligible_support() -> None:
    provider = OfficialLawProvider(
        FixtureTransport(_archive(abandoned=True)), verify_webpage=False
    )

    result, source, evidence = asyncio.run(provider.exact_lookup("示範程序法", "12-1"))

    assert result.metadata["repealed"] is True
    assert source is not None and source.warnings == ["LAW_REPEALED"]
    assert evidence is not None and not evidence.eligible_for_claim_support


def test_official_law_transport_error_is_not_not_found() -> None:
    provider = OfficialLawProvider(
        FixtureTransport(b"unavailable", status_code=503), verify_webpage=False
    )

    result, source, evidence = asyncio.run(provider.exact_lookup("示範程序法", "1"))

    assert result.status == ProviderResultStatus.ERROR
    assert result.error_code == ProviderErrorCode.OFFICIAL_SOURCE_UNAVAILABLE
    assert source is None and evidence is None


def test_official_law_archive_rejects_paths() -> None:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("nested/ChLaw.json", "{}")

    with pytest.raises(ValueError, match="ARCHIVE_PATH_FORBIDDEN"):
        OfficialLawProvider.parse_archive(buffer.getvalue())


def test_structured_and_web_content_conflict_cannot_be_final_evidence() -> None:
    provider = OfficialLawProvider(
        ArchiveThenPageTransport("<html><body>不同的官方網頁內容</body></html>")
    )

    result, source, evidence = asyncio.run(provider.exact_lookup("示範程序法", "12-1"))

    assert result.status == ProviderResultStatus.ERROR
    assert result.error_code == ProviderErrorCode.OFFICIAL_CONTENT_CONFLICT
    assert source is not None and source.trust_status == TrustStatus.VERIFICATION_FAILED
    assert evidence is not None and not evidence.eligible_for_claim_support


def test_structured_and_web_content_match_remains_eligible() -> None:
    provider = OfficialLawProvider(
        ArchiveThenPageTransport(
            "<html><body><p>合成測試資料不得作為真實法律意見。</p></body></html>"
        )
    )

    result, source, evidence = asyncio.run(provider.exact_lookup("示範程序法", "12-1"))

    assert result.status == ProviderResultStatus.FOUND
    assert source is not None and source.trust_status == TrustStatus.EVIDENCE_ELIGIBLE
    assert evidence is not None and evidence.eligible_for_claim_support
