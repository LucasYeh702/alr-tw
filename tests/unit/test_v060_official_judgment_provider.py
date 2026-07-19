from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Mapping
from urllib.parse import quote

from alr_tw.contracts.providers import ProviderErrorCode, ProviderResultStatus
from alr_tw.contracts.sources import EvidenceSectionType, TrustStatus
from alr_tw.providers.official.judgments import (
    JUDGMENT_ADVANCED_SEARCH_URL,
    JUDGMENT_DATA_URL,
    JUDGMENT_SEARCH_URL,
    OfficialJudgmentProvider,
)
from alr_tw.providers.official.judicial_site import JudicialSiteResponse

JID = "TSDM,130,測訴,42,20410102,1"


def _detail_page(jid: str = JID, *, title: str = "臺灣示範地方法院刑事判決") -> str:
    encoded = quote(jid, safe="")
    return f"""
    <html><head><title>{title}</title></head><body>
      <a id="hlPrint" href="/FJUD/printData.aspx?id={encoded}">列印</a>
      <div id="jud">
        <div class="row"><div class="col-th">裁判字號：</div><div class="col-td">{title}</div></div>
        <div class="row"><div class="col-th">裁判日期：</div><div class="col-td">民國 130 年 1 月 2 日</div></div>
        <div class="row"><div class="col-th">裁判案由：</div><div class="col-td">合成資料測試</div></div>
        <div class="jud_content"><div class="htmlcontent">
          <div>臺灣示範地方法院刑事判決</div>
          <div>130年度測訴字第42號</div>
          <div>主 文</div>
          <div>合成裁判結果。</div>
          <div>理 由</div>
          <div>一、本文件僅供軟體測試。</div>
          <div>二、不得視為真實裁判。</div>
        </div></div>
      </div>
    </body></html>
    """


def _search_form() -> str:
    return """
    <form id="form1" action="./Default_AD.aspx">
      <input type="hidden" name="__VIEWSTATE" value="fixture-state">
      <input type="hidden" name="__EVENTVALIDATION" value="fixture-validation">
      <input type="hidden" name="__VIEWSTATEGENERATOR" value="fixture-generator">
      <input type="hidden" name="judtype" value="JUDBOOK">
    </form>
    """


def _result_frame(token: str = "fixture-token", count: int = 1) -> str:
    return f"""
    <a href="qryresultlst.aspx?ty=JUDBOOK&amp;q={token}">查詢結果<span class="badge">{count}</span></a>
    <iframe name="iframe-data" src="qryresultlst.aspx?ty=JUDBOOK&amp;q={token}"></iframe>
    """


def _result_list(*jids: str) -> str:
    rows: list[str] = []
    for index, jid in enumerate(jids, start=1):
        encoded = quote(jid, safe="")
        rows.append(
            f'<tr><td><a href="data.aspx?ty=JD&amp;id={encoded}&amp;ot=in">'
            f"臺灣示範地方法院 130 年度測訴字第 42 號刑事判決 {index}</a></td></tr>"
            f'<tr><td><span class="tdCut">合成搜尋摘要 {index}</span></td></tr>'
        )
    return f"<table>{''.join(rows)}</table>"


def _response(document: str, *, status: int = 200, url: str = "https://example.invalid") -> JudicialSiteResponse:
    return JudicialSiteResponse(status, document.encode(), {}, url)


class FixtureSiteTransport:
    def __init__(self, responses: list[JudicialSiteResponse]):
        self.responses = responses
        self.calls: list[tuple[str, str, Mapping[str, str] | None]] = []
        self.open_count = 0
        self.close_count = 0

    async def open(self) -> None:
        self.open_count += 1

    async def close(self) -> None:
        self.close_count += 1

    async def get(self, url: str, *, timeout: float, max_bytes: int) -> JudicialSiteResponse:
        assert timeout > 0 and max_bytes > 0
        self.calls.append(("GET", url, None))
        return self.responses.pop(0)

    async def post_form(
        self,
        url: str,
        form: Mapping[str, str],
        *,
        timeout: float,
        max_bytes: int,
    ) -> JudicialSiteResponse:
        assert timeout > 0 and max_bytes > 0
        self.calls.append(("POST", url, dict(form)))
        return self.responses.pop(0)


def test_official_judgment_exact_lookup_creates_sectioned_website_snapshot() -> None:
    transport = FixtureSiteTransport([_response(_detail_page())])
    provider = OfficialJudgmentProvider(transport)

    result, source, evidence = asyncio.run(
        provider.exact_lookup(JID, now=datetime(2041, 1, 3, tzinfo=UTC))
    )

    assert transport.calls[0][0] == "GET"
    assert transport.calls[0][1].startswith(JUDGMENT_DATA_URL)
    assert "id=TSDM%2C130%2C" in transport.calls[0][1]
    assert result.status == ProviderResultStatus.FOUND
    assert source is not None and source.trust_status == TrustStatus.EVIDENCE_ELIGIBLE
    assert source.official_url.startswith(JUDGMENT_DATA_URL)
    assert source.metadata["retrieval"] == "official_website_html"
    assert evidence[0].section_type == EvidenceSectionType.DISPOSITION
    assert evidence[0].exact_text == "合成裁判結果。"
    assert evidence[1].exact_text == "一、本文件僅供軟體測試。"


def test_judgment_party_argument_is_not_labelled_as_court_reasoning() -> None:
    segments = OfficialJudgmentProvider.segment_reasoning_roles(
        "上訴人主張：原判決不當。\n本院審酌後認上訴無理由。"
    )

    assert segments == [
        (EvidenceSectionType.PARTY_ARGUMENT, "上訴人主張：原判決不當。"),
        (EvidenceSectionType.COURT_REASONING, "本院審酌後認上訴無理由。"),
    ]


def test_official_judgment_accepts_only_an_allowlisted_detail_url() -> None:
    transport = FixtureSiteTransport([_response(_detail_page())])
    provider = OfficialJudgmentProvider(transport)
    official_url = OfficialJudgmentProvider.official_document_url(JID)

    result, source, _ = asyncio.run(provider.exact_lookup(official_url))

    assert result.status == ProviderResultStatus.FOUND
    assert source is not None and source.official_identifier == JID
    result, _, _ = asyncio.run(provider.exact_lookup("https://attacker.invalid/FJUD/data.aspx?id=x"))
    assert result.error_code == ProviderErrorCode.INVALID_IDENTIFIER


def test_official_removed_judgment_requires_local_removal() -> None:
    transport = FixtureSiteTransport([_response("<html>查無資料</html>", status=404)])
    provider = OfficialJudgmentProvider(transport)

    result, source, evidence = asyncio.run(provider.exact_lookup(JID))

    assert result.status == ProviderResultStatus.NOT_FOUND
    assert result.error_code == ProviderErrorCode.OFFICIAL_SOURCE_NOT_FOUND
    assert result.metadata["removal_required"] is True
    assert source is None and evidence == []


def test_official_judgment_page_schema_failure_is_not_not_found() -> None:
    provider = OfficialJudgmentProvider(FixtureSiteTransport([_response("<html>changed</html>")]))

    result, source, evidence = asyncio.run(provider.exact_lookup(JID))

    assert result.status == ProviderResultStatus.ERROR
    assert result.error_code == ProviderErrorCode.OFFICIAL_PARSE_ERROR
    assert source is None and evidence == []


def test_official_judgment_identifier_mismatch_fails_closed() -> None:
    other = "TSDM,130,測訴,43,20410102,1"
    provider = OfficialJudgmentProvider(
        FixtureSiteTransport([_response(_detail_page(other))])
    )

    result, source, evidence = asyncio.run(provider.exact_lookup(JID))

    assert result.error_code == ProviderErrorCode.OFFICIAL_IDENTIFIER_MISMATCH
    assert source is None and evidence == []


def test_jid_normalization_is_strict() -> None:
    assert OfficialJudgmentProvider.normalize_jid(f" {JID} ") == JID
    assert OfficialJudgmentProvider.normalize_jid("TSDM,130,測訴,42,20410102") is None
    assert OfficialJudgmentProvider.normalize_jid("https://attacker.invalid/value") is None


def test_formal_citation_resolves_then_downloads_official_html() -> None:
    resolved_jid = "TPSV,130,測上,930,20410103,1"
    detail = _detail_page(resolved_jid, title="最高法院 130 年度測上字第 930 號民事判決")
    transport = FixtureSiteTransport(
        [_response(_result_frame()), _response(_result_list(resolved_jid)), _response(detail)]
    )
    provider = OfficialJudgmentProvider(transport)

    result, source, _ = asyncio.run(
        provider.exact_lookup("最高法院 130 年度測上字第 930 號民事判決")
    )

    assert result.status == ProviderResultStatus.FOUND
    assert source is not None and source.official_identifier == resolved_jid
    assert "jud_sys=V" in transport.calls[0][1]
    assert transport.calls[-1][1].startswith(JUDGMENT_DATA_URL)


def test_ambiguous_formal_citation_fails_closed() -> None:
    jid_v = "TPSV,130,測上,930,20410103,1"
    jid_m = "TPSM,130,測上,930,20410104,1"
    transport = FixtureSiteTransport(
        [
            _response(_result_frame("all", count=2)),
            _response(_result_list(jid_v, jid_m)),
        ]
    )
    provider = OfficialJudgmentProvider(transport)

    result, source, evidence = asyncio.run(
        provider.exact_lookup("最高法院130年度測上字第930號")
    )

    assert result.status == ProviderResultStatus.ERROR
    assert result.error_code == ProviderErrorCode.AMBIGUOUS_FORMAL_CITATION
    assert result.metadata["candidate_jids"] == [jid_m, jid_v]
    assert source is None and evidence == []


def test_keyword_search_posts_official_form_and_returns_unverified_candidates() -> None:
    transport = FixtureSiteTransport(
        [_response(_search_form()), _response(_result_frame()), _response(_result_list(JID))]
    )
    provider = OfficialJudgmentProvider(transport)

    result = asyncio.run(
        provider.search(
            "侵權行為 損害賠償",
            court="臺灣臺北地方法院",
            case_type="民事",
            year_from=120,
            year_to=130,
            main_text="原告之訴駁回",
        )
    )

    assert result.status == ProviderResultStatus.FOUND
    assert len(result.candidates) == 1
    assert result.candidates[0].official_identifier == JID
    assert result.candidates[0].metadata["candidate_tier"] == "official_search_result"
    method, url, form = transport.calls[1]
    assert method == "POST" and url == JUDGMENT_ADVANCED_SEARCH_URL
    assert form is not None
    assert form["jud_kw"] == "侵權行為 損害賠償"
    assert form["jud_court"] == "TPD"
    assert form["jud_sys"] == "V"
    assert form["dy1"] == "120" and form["dy2"] == "130"
    assert transport.open_count == transport.close_count == 1


def test_search_hit_parser_stops_at_requested_candidate_cap() -> None:
    jids = (
        "TSDM,130,測訴,41,20410101,1",
        "TSDM,130,測訴,42,20410102,1",
        "TSDM,130,測訴,43,20410103,1",
    )

    hits = OfficialJudgmentProvider.parse_search_hits(_result_list(*jids), limit=2)

    assert [hit.jid for hit in hits] == list(jids[:2])


def test_precise_search_uses_get_without_posting_form() -> None:
    transport = FixtureSiteTransport(
        [_response(_result_frame()), _response(_result_list(JID))]
    )
    provider = OfficialJudgmentProvider(transport)

    result = asyncio.run(
        provider.search(
            case_word="測訴",
            case_number="42",
            year_from=130,
            year_to=130,
            case_type="刑事",
        )
    )

    assert result.status == ProviderResultStatus.FOUND
    assert all(method == "GET" for method, _, _ in transport.calls)
    assert transport.calls[0][1].startswith(JUDGMENT_SEARCH_URL)
    assert "jud_case=" in transport.calls[0][1]


def test_waf_rejection_is_distinct_from_not_found() -> None:
    provider = OfficialJudgmentProvider(
        FixtureSiteTransport([_response("Request Rejected", status=200)])
    )

    result, source, evidence = asyncio.run(provider.exact_lookup(JID))

    assert result.status == ProviderResultStatus.ERROR
    assert result.error_code == ProviderErrorCode.OFFICIAL_SOURCE_BLOCKED
    assert source is None and evidence == []


def test_health_check_probes_search_form_without_credentials() -> None:
    provider = OfficialJudgmentProvider(FixtureSiteTransport([_response(_search_form())]))

    health = asyncio.run(provider.health_check())

    assert health.status.value == "healthy"
    assert health.error_code is None


def test_search_validation_rejects_partial_case_identifier_without_network() -> None:
    transport = FixtureSiteTransport([])
    provider = OfficialJudgmentProvider(transport)

    result = asyncio.run(provider.search(case_word="台上"))

    assert result.status == ProviderResultStatus.ERROR
    assert result.error_code == ProviderErrorCode.INVALID_IDENTIFIER
    assert transport.calls == []
