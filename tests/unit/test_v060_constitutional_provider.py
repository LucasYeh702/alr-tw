from __future__ import annotations

import asyncio
import html
import json
from datetime import UTC, datetime

from alr_tw.contracts.providers import ProviderErrorCode, ProviderResultStatus
from alr_tw.contracts.sources import EvidenceSectionType, TrustStatus
from alr_tw.providers.official.constitutional import (
    INTERPRETATION_LIST_URL,
    JUDGMENT_LIST_URL,
    SUBSTANTIVE_RULING_LIST_URL,
    OfficialConstitutionalProvider,
)
from alr_tw.providers.official.http import HttpResponse


def _index_html() -> str:
    return """
    <a target="_blank" href="/docdata.aspx?fid=38&amp;id=900001"
       title="130年憲判字第2號"><p>130年憲判字</p><p>第2號</p></a>
    """


def _detail_html() -> str:
    embedded = {
        "atts": [
            {
                "doc_att_title": "憲法法庭130年憲判字第2號協同意見書",
                "doc_att_txt": "本段是合成協同意見，不代表法庭多數意見。",
            },
            {
                "doc_att_title": "憲法法庭130年憲判字第2號部分不同意見書",
                "doc_att_txt": "本段是合成不同意見，不代表法庭多數意見。",
            },
        ]
    }
    return f"""
    <li class="title">判決字號</li><li class="text">130年憲判字第2號</li>
    <li class="title">判決日期</li><li class="text">130年01月02日</li>
    <li class="title">案由</li><li class="text">合成資料邊界案</li>
    <li class="title">主文</li><li class="text"><ul><li><pre>合成主文。</pre></li></ul></li>
    <li class="title">理由</li><li class="text"><ul><li><pre>合成多數理由。</pre></li></ul></li>
    <textarea id="jsonLabel">{html.escape(json.dumps(embedded, ensure_ascii=False))}</textarea>
    """


class RoutingTransport:
    async def get(self, url: str, *, timeout: float, max_bytes: int) -> HttpResponse:
        del timeout, max_bytes
        if url.startswith(JUDGMENT_LIST_URL):
            payload = _index_html().encode()
        elif "id=900001" in url:
            payload = _detail_html().encode()
        else:
            return HttpResponse(404, b"", {}, url)
        return HttpResponse(200, payload, {}, url)


class InterpretationTransport:
    async def get(self, url: str, *, timeout: float, max_bytes: int) -> HttpResponse:
        del timeout, max_bytes
        if url.startswith(JUDGMENT_LIST_URL):
            payload = b"<html></html>"
        elif url.startswith(INTERPRETATION_LIST_URL):
            payload = (
                '<li><a target="_blank" title="\u91cb\u5b57\u7b2c999\u865f" '
                'href="/docdata.aspx?fid=100&amp;id=999001">999</a></li>'
            ).encode()
        elif "id=999001" in url:
            payload = """
            <li class="title">解釋字號</li><li class="text">釋字第999號</li>
            <li class="title">解釋公布院令</li><li class="text">合成日期</li>
            <li class="title">解釋爭點</li><li class="text">合成爭點</li>
            <li class="title">解釋文</li><li class="text"><ul><li><pre>合成解釋文。</pre></li></ul></li>
            <li class="title">理由書</li><li class="text"><ul><li><pre>合成理由書。</pre></li></ul></li>
            """.encode()
        else:
            return HttpResponse(404, b"", {}, url)
        return HttpResponse(200, payload, {}, url)


class SubstantiveRulingTransport:
    async def get(self, url: str, *, timeout: float, max_bytes: int) -> HttpResponse:
        del timeout, max_bytes
        if url.startswith(JUDGMENT_LIST_URL):
            payload = b"<html></html>"
        elif url.startswith(SUBSTANTIVE_RULING_LIST_URL):
            payload = (
                '<div class="cont" title="113年憲暫裁字第1號(原分案號)">'
                '<a href="/docdata.aspx?fid=39&amp;id=900039">'
                "113年憲暫裁字第1號(原分案號)</a></div>"
            ).encode()
        elif "id=900039" in url:
            payload = """
            <li class="title">裁定字號</li><li class="text">113年憲暫裁字第1號</li>
            <li class="title">裁定日期</li><li class="text">合成日期</li>
            <li class="title">案由</li><li class="text">合成暫時處分案</li>
            <li class="title">主文</li><li class="text"><ul><li><pre>合成裁定主文。</pre></li></ul></li>
            <li class="title">理由</li><li class="text"><ul><li><pre>合成裁定理由。</pre></li></ul></li>
            """.encode()
        elif url.startswith(INTERPRETATION_LIST_URL):
            payload = b"<html></html>"
        else:
            return HttpResponse(404, b"", {}, url)
        return HttpResponse(200, payload, {}, url)


def test_constitutional_exact_lookup_separates_court_and_individual_opinions() -> None:
    provider = OfficialConstitutionalProvider(RoutingTransport())

    result, source, evidence = asyncio.run(
        provider.exact_lookup(
            "130 年 憲判字 第 02 號",
            now=datetime(2041, 1, 3, tzinfo=UTC),
        )
    )

    assert result.status == ProviderResultStatus.FOUND
    assert source is not None and source.trust_status == TrustStatus.EVIDENCE_ELIGIBLE
    assert [item.section_type for item in evidence] == [
        EvidenceSectionType.HOLDING,
        EvidenceSectionType.COURT_REASONING,
        EvidenceSectionType.CONCURRING_OPINION,
        EvidenceSectionType.DISSENTING_OPINION,
    ]
    assert evidence[2].exact_text not in source.normalized_text
    assert evidence[3].exact_text not in source.normalized_text


def test_constitutional_keyword_search_uses_official_index() -> None:
    provider = OfficialConstitutionalProvider(RoutingTransport())

    result = asyncio.run(provider.search("130年憲判字"))

    assert result.status == ProviderResultStatus.FOUND
    assert result.metadata["matches"][0]["identifier"] == "130年憲判字第2號"


def test_constitutional_invalid_identifier_is_not_network_not_found() -> None:
    provider = OfficialConstitutionalProvider(RoutingTransport())

    result, source, evidence = asyncio.run(provider.exact_lookup("沒有可辨識字號"))

    assert result.status == ProviderResultStatus.ERROR
    assert result.error_code == ProviderErrorCode.INVALID_IDENTIFIER
    assert source is None and evidence == []


def test_constitutional_official_not_found_is_classified() -> None:
    provider = OfficialConstitutionalProvider(RoutingTransport())

    result, source, evidence = asyncio.run(provider.exact_lookup("130年憲判字第99號"))

    assert result.status == ProviderResultStatus.NOT_FOUND
    assert result.error_code == ProviderErrorCode.OFFICIAL_SOURCE_NOT_FOUND
    assert source is None and evidence == []


def test_constitutional_interpretation_uses_distinct_holding_and_reasoning() -> None:
    provider = OfficialConstitutionalProvider(InterpretationTransport())

    result, source, evidence = asyncio.run(provider.exact_lookup("釋字第999號"))

    assert result.status == ProviderResultStatus.FOUND
    assert source is not None and source.official_identifier == "釋字第999號"
    assert evidence[0].section_type == EvidenceSectionType.HOLDING
    assert evidence[0].exact_text == "合成解釋文。"
    assert evidence[1].section_type == EvidenceSectionType.COURT_REASONING
    assert evidence[1].exact_text == "合成理由書。"


def test_constitutional_substantive_ruling_is_indexed_from_anchor_text() -> None:
    provider = OfficialConstitutionalProvider(SubstantiveRulingTransport())

    result, source, evidence = asyncio.run(provider.exact_lookup("113年憲暫裁字第1號"))

    assert result.status == ProviderResultStatus.FOUND
    assert source is not None and source.official_identifier == "113年憲暫裁字第1號"
    assert evidence[0].section_type == EvidenceSectionType.HOLDING
