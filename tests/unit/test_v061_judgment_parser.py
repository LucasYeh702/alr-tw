from datetime import UTC, datetime
from urllib.parse import quote

from alr_tw.contracts.sources import EvidenceSectionType, TrustStatus
from alr_tw.providers.official.judgment_parser import (
    JudgmentParseStatus,
    JudgmentRole,
    extract_judgment_blocks,
    parse_judgment_blocks,
)
from alr_tw.providers.official.judgments import OfficialJudgmentProvider


JID = "TSTV,130,勞,8,20990102,1"


def _page(body: str) -> str:
    encoded = quote(JID, safe="")
    return f"""
    <html><head><title>臺灣示範地方法院民事判決</title></head><body>
      <a id="hlPrint" href="/FJUD/printData.aspx?id={encoded}">列印</a>
      <div id="jud">
        <div class="row"><div class="col-th">裁判字號：</div><div class="col-td">130年度勞字第8號</div></div>
        <div class="jud_content"><div class="htmlcontent">{body}</div></div>
      </div>
    </body></html>
    """


def test_recursive_extraction_preserves_nested_blocks_and_ignores_controls() -> None:
    soup = OfficialJudgmentProvider._soup(
        '<div class="htmlcontent"><div>主<br>文</div><section><p>第一行</p>'
        '<div><span>第二行</span></div></section><script>secret()</script>'
        '<div style="display:none">隱藏內容</div></div>'
    )
    blocks = extract_judgment_blocks(soup.select_one(".htmlcontent"))
    assert blocks == ["主", "文", "第一行", "第二行"]
    assert "secret" not in "\n".join(blocks)
    assert "隱藏內容" not in "\n".join(blocks)

    parsed = parse_judgment_blocks(
        [*blocks, "理由", "本院認為請求無理由。"], canonical_jid=JID
    )
    assert parsed.sections[0].role is JudgmentRole.DISPOSITION


def test_text_pre_preserves_newline_boundaries() -> None:
    soup = OfficialJudgmentProvider._soup(
        '<div class="text-pre">主 文\n合成結果。\n理 由\n本院認為合成請求有理由。</div>'
    )

    blocks = extract_judgment_blocks(soup.select_one(".text-pre"))
    parsed = parse_judgment_blocks(blocks, canonical_jid=JID)

    assert blocks == ["主 文", "合成結果。", "理 由", "本院認為合成請求有理由。"]
    assert parsed.parse_status is JudgmentParseStatus.COMPLETE


def test_nested_pre_and_raw_container_text_preserve_newline_boundaries() -> None:
    for document in (
        '<div class="htmlcontent"><pre>主文\n駁回。\n理由\n本院認為無理由。</pre></div>',
        '<div class="htmlcontent">主文\n駁回。\n理由\n本院認為無理由。</div>',
    ):
        soup = OfficialJudgmentProvider._soup(document)

        blocks = extract_judgment_blocks(soup.select_one(".htmlcontent"))
        parsed = parse_judgment_blocks(blocks, canonical_jid=JID)

        assert blocks == ["主文", "駁回。", "理由", "本院認為無理由。"]
        assert parsed.parse_status is JudgmentParseStatus.COMPLETE


def test_non_pre_source_wrapping_is_normalized_without_splitting_a_paragraph() -> None:
    soup = OfficialJudgmentProvider._soup(
        '<div class="htmlcontent">法院認為契約應\n    繼續履行。</div>'
    )

    blocks = extract_judgment_blocks(soup.select_one(".htmlcontent"))

    assert blocks == ["法院認為契約應 繼續履行。"]


def test_combined_heading_is_partial_until_safe_court_heading_appears() -> None:
    parsed = parse_judgment_blocks(
        [
            "主文",
            "原告之訴駁回。",
            "事實及理由",
            "一、原告主張雇主違法解僱。",
            "二、被告辯稱解僱合法。",
            "三、本院之判斷",
            "勞動契約終止仍應符合比例原則。",
        ],
        canonical_jid=JID,
    )
    assert parsed.parse_status is JudgmentParseStatus.COMPLETE
    roles = [item.role for item in parsed.sections]
    assert roles == [
        JudgmentRole.DISPOSITION,
        JudgmentRole.PARTY_ARGUMENT,
        JudgmentRole.PARTY_ARGUMENT,
        JudgmentRole.COURT_HOLDING,
    ]
    assert parsed.sections[1].eligible_for_claim_support is False
    assert parsed.sections[2].eligible_for_claim_support is False
    assert parsed.sections[3].eligible_for_claim_support is True


def test_party_argument_prefixed_by_court_marker_is_never_promoted() -> None:
    parsed = parse_judgment_blocks(
        [
            "主文",
            "原告之訴駁回。",
            "事實及理由",
            "一、按原告起訴主張：被告違法解僱。",
            "二、被告則以：解僱係屬合法。",
            "三、本院之判斷",
            "原告請求無理由。",
        ],
        canonical_jid=JID,
    )

    assert [item.role for item in parsed.sections] == [
        JudgmentRole.DISPOSITION,
        JudgmentRole.PARTY_ARGUMENT,
        JudgmentRole.PARTY_ARGUMENT,
        JudgmentRole.COURT_HOLDING,
    ]
    assert all(not item.eligible_for_claim_support for item in parsed.sections[1:3])
    assert parsed.sections[3].eligible_for_claim_support is True


def test_court_rebuttal_of_party_position_remains_court_reasoning() -> None:
    parsed = parse_judgment_blocks(
        [
            "主文",
            "原告之訴駁回。",
            "事實及理由",
            "查原告主張被告違法解僱云云，自無足採。",
        ],
        canonical_jid=JID,
    )

    rebuttal = parsed.sections[-1]
    assert rebuttal.role is JudgmentRole.COURT_REASONING
    assert rebuttal.confidence == "high"
    assert rebuttal.eligible_for_claim_support is True


def test_party_position_with_rebuttal_words_remains_party_argument() -> None:
    parsed = parse_judgment_blocks(
        [
            "事實及理由",
            "被告辯稱原告之請求為無理由。",
            "被告抗辯原告主張之金額不足採。",
        ],
        canonical_jid=JID,
    )

    assert all(item.role is JudgmentRole.PARTY_ARGUMENT for item in parsed.sections)
    assert all(not item.eligible_for_claim_support for item in parsed.sections)


def test_unclassified_combined_heading_text_is_preserved_not_promoted() -> None:
    parsed = parse_judgment_blocks(
        ["事實及理由", "雙方於某日簽訂契約。"], canonical_jid=JID
    )
    assert parsed.parse_status is JudgmentParseStatus.PARTIAL
    assert parsed.sections[0].role is JudgmentRole.UNKNOWN
    assert parsed.sections[0].eligible_for_claim_support is False
    assert parsed.unparsed_remainder == "雙方於某日簽訂契約。"
    assert "JUDGMENT_PARSE_PARTIAL" in parsed.warnings


def test_provider_preserves_partial_official_source_without_eligible_evidence() -> None:
    parsed = OfficialJudgmentProvider.parse_detail_page(
        _page("<div>事實及理由</div><div>雙方於某日簽訂契約。</div>"),
        expected_jid=JID,
        official_url=OfficialJudgmentProvider.official_document_url(JID),
    )
    provider = OfficialJudgmentProvider()
    source, evidence = provider._build_snapshot(parsed, datetime(2041, 1, 3, tzinfo=UTC))
    assert source.trust_status is TrustStatus.OFFICIAL_VERIFIED
    assert source.metadata["parse_status"] == "partial"
    assert source.metadata["eligible_span_count"] == 0
    assert "JUDGMENT_COURT_REASONING_MISSING" in source.warnings
    assert evidence
    assert all(not item.eligible_for_claim_support for item in evidence)
    assert evidence[0].section_type is EvidenceSectionType.UNKNOWN


def test_provider_keeps_party_arguments_ineligible_in_complete_source() -> None:
    parsed = OfficialJudgmentProvider.parse_detail_page(
        _page(
            "<div>主文</div><div>原告之訴駁回。</div>"
            "<div>事實及理由</div>"
            "<div>一、原告主張被告違法。</div>"
            "<div>二、本院之判斷</div><div>原告請求無理由。</div>"
        ),
        expected_jid=JID,
        official_url=OfficialJudgmentProvider.official_document_url(JID),
    )
    source, evidence = OfficialJudgmentProvider()._build_snapshot(
        parsed, datetime(2041, 1, 3, tzinfo=UTC)
    )
    assert source.trust_status is TrustStatus.EVIDENCE_ELIGIBLE
    party = next(item for item in evidence if item.section_type is EvidenceSectionType.PARTY_ARGUMENT)
    reasoning = next(item for item in evidence if item.section_type is EvidenceSectionType.COURT_HOLDING)
    assert party.eligible_for_claim_support is False
    assert reasoning.eligible_for_claim_support is True
