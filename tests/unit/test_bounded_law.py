import asyncio
from datetime import date

import pytest

from alr_tw.contracts.historical_law import HistoricalLawQuery
from alr_tw.providers.official.bounded_law import (
    OfficialHistoricalLawProvider,
    OfficialInterpretationProvider,
)
from alr_tw.providers.official.http import HttpResponse


class Transport:
    def __init__(self, html):
        self.html = html

    async def get(self, url, **kwargs):
        return HttpResponse(200, self.html.encode(), {}, url)


HISTORY = '<table><tr><th>法規名稱：</th><td>民法</td></tr><tr><th>修正日期：</th><td>民國 110 年 01 月 20 日</td></tr></table><div class="row"><div class="col-no">第 12 條</div><div class="col-data">滿合成歲數為成年。</div></div>'


def query(**updates):
    return HistoricalLawQuery(
        query_id="synthetic-query",
        law_identifier="B0000001",
        as_of_date=updates.get("as_of_date", date(2021, 2, 1)),
        bounded_scope="synthetic-article-12",
    )


def interpretation(note=""):
    fields = {
        "發文單位": "合成機關",
        "發文字號": "合成字第 1 號",
        "發文日期": "民國 110 年 01 月 20 日",
    }
    if note:
        fields["效力註記"] = note
    return (
        "".join(
            f'<div class="col-row"><div class="col-th">{k}：</div><div class="col-td">{v}</div></div>'
            for k, v in fields.items()
        )
        + '<div id="cp_content_EFULLtr"><pre>全文內容：本合成函釋全文，不是法律或法院見解。</pre></div>'
    )


def test_historical_text_does_not_establish_effective_or_case_applicable_date():
    result = asyncio.run(OfficialHistoricalLawProvider(Transport(HISTORY)).lookup(query(), "12"))
    source = result.provider_result.sources[0]
    assert source.effective_from is None
    assert source.metadata["version_date"] == "2021-01-20"
    assert source.metadata["applicability_status"] == "requires_server_adjudication"
    assert not result.provider_result.coverage_complete


@pytest.mark.parametrize("as_of", [date(2010, 1, 1), date(2026, 1, 1)])
def test_outside_scope_not_reported_as_absence(as_of):
    result = asyncio.run(
        OfficialHistoricalLawProvider(Transport(HISTORY)).lookup(query(as_of_date=as_of), "12")
    )
    assert result.provider_result.reason_codes == ["HISTORICAL_SCOPE_UNSUPPORTED"]
    assert not result.provider_result.absence_claim_allowed


def test_historical_wrong_version_or_ambiguous_article_rejected():
    for html in [HISTORY.replace("110 年", "109 年"), HISTORY + HISTORY]:
        with pytest.raises(ValueError):
            asyncio.run(OfficialHistoricalLawProvider(Transport(html)).lookup(query(), "12"))


def test_interpretation_exact_identity_fulltext_and_unknown_effect():
    provider = OfficialInterpretationProvider(Transport(interpretation()))
    result = asyncio.run(provider.lookup("FE000001", "合成字第1號"))
    source = result.sources[0]
    assert source.source_role.value == "interpretive_guidance"
    assert source.metadata["effectivity_status"] == "unknown"
    with pytest.raises(ValueError, match="IDENTITY_MISMATCH"):
        asyncio.run(provider.lookup("FE000001", "合成字第2號"))
    with pytest.raises(ValueError, match="FULLTEXT_REQUIRED"):
        asyncio.run(
            OfficialInterpretationProvider(
                Transport(interpretation().replace("cp_content_EFULLtr", "summary"))
            ).lookup("FE000001", "合成字第1號")
        )


@pytest.mark.parametrize(
    "note,status", [("部分停止適用", "partially_stopped"), ("由新函取代", "superseded")]
)
def test_explicit_effectivity_not_inferred_from_body(note, status):
    result = asyncio.run(
        OfficialInterpretationProvider(Transport(interpretation(note))).lookup(
            "FE000001", "合成字第1號"
        )
    )
    assert result.sources[0].metadata["effectivity_status"] == status


def test_historical_missing_article_is_incomplete_not_authoritative_absence():
    result = asyncio.run(OfficialHistoricalLawProvider(Transport(HISTORY)).lookup(query(), "999"))
    assert result.provider_result.status.value == "blocked"
    assert result.provider_result.reason_codes == ["HISTORICAL_ARTICLE_NOT_FOUND_IN_VERSION"]
    assert not result.provider_result.coverage_complete
    assert not result.provider_result.absence_claim_allowed


@pytest.mark.parametrize("html", [
    HISTORY.replace("民法", "其他法"),
    HISTORY.replace("修正日期", "本文日期"),
    HISTORY.replace("修正日期", "本文日期") + "民國 110 年 01 月 20 日",
])
def test_historical_requires_explicit_page_identity_and_version(html):
    with pytest.raises(ValueError, match="HISTORICAL_"):
        asyncio.run(OfficialHistoricalLawProvider(Transport(html)).lookup(query(), "12"))


@pytest.mark.parametrize("note", ["是否已由新函取代尚待確認", "僅說明部分條文", "未被取代", "—"])
def test_uncertain_effectivity_metadata_stays_unknown(note):
    result = asyncio.run(OfficialInterpretationProvider(Transport(interpretation(note))).lookup(
        "FE000001", "合成字第1號"
    ))
    assert result.sources[0].metadata["effectivity_status"] == "unknown"
    assert "INTERPRETATION_EFFECTIVITY_UNKNOWN" in result.reason_codes


def test_placeholder_repeal_date_stays_unknown():
    html = interpretation() + '<div class="col-row"><div class="col-th">廢止日期：</div><div class="col-td">—</div></div>'
    result = asyncio.run(OfficialInterpretationProvider(Transport(html)).lookup("FE000001", "合成字第1號"))
    assert result.sources[0].metadata["effectivity_status"] == "unknown"
