from __future__ import annotations

import json
import re
import ssl
from datetime import UTC, date, datetime, timedelta
from typing import Any
from urllib.parse import parse_qs, urlparse

import pytest

from alr_tw.contracts.historical_law import (
    HistoricalLawQuery,
    LegislativeMaterialRole,
    LegislativeStage,
    validate_historical_law_resolution,
)
from alr_tw.contracts.public_law import (
    PublicLawResultStatus,
    PublicLawServerMetadata,
    PublicLawValidationDecision,
)
from alr_tw.providers.legislative_yuan import (
    DATASET_PAGE_SIZE,
    LEGISLATIVE_YUAN_ALLOWED_HOSTS,
    LEGISLATIVE_YUAN_ARTICLE_COMPARISON_DATASET,
    LEGISLATIVE_YUAN_CAUCUS_DATASET,
    LEGISLATIVE_YUAN_COMMITTEE_DATASET,
    LEGISLATIVE_YUAN_DATA_HOST,
    LEGISLATIVE_YUAN_PROPOSAL_DATASET,
    LEGISLATIVE_YUAN_THIRD_READING_DATASET,
    LEGISLATIVE_YUAN_UNSUPPORTED_DATASET_IDS,
    LegislativeYuanDataBackend,
    LegislativeYuanHttpClient,
    LegislativeYuanProviderAdapter,
    _official_ssl_context,
)
from alr_tw.providers.official.http import HttpResponse


NOW = datetime(2026, 8, 20, 8, 0, tzinfo=UTC)
DATASET_IDS = (
    LEGISLATIVE_YUAN_PROPOSAL_DATASET,
    LEGISLATIVE_YUAN_ARTICLE_COMPARISON_DATASET,
    LEGISLATIVE_YUAN_COMMITTEE_DATASET,
    LEGISLATIVE_YUAN_CAUCUS_DATASET,
    LEGISLATIVE_YUAN_THIRD_READING_DATASET,
)


class FixtureTransport:
    def __init__(
        self,
        responses: dict[str, object] | None = None,
        *,
        error: Exception | None = None,
        redirect_url: str | None = None,
        raw_content: bytes | None = None,
        content_type: str | None = "application/json",
    ) -> None:
        self.responses = responses or {}
        self.error = error
        self.redirect_url = redirect_url
        self.raw_content = raw_content
        self.content_type = content_type
        self.calls: list[tuple[str, float, int]] = []

    def get(self, url: str, *, timeout: float, max_bytes: int) -> HttpResponse:
        self.calls.append((url, timeout, max_bytes))
        if self.error is not None:
            raise self.error
        if self.redirect_url is not None:
            return HttpResponse(200, b'{"dataList": []}', {}, self.redirect_url)
        if self.raw_content is not None:
            headers = {} if self.content_type is None else {"Content-Type": self.content_type}
            return HttpResponse(200, self.raw_content, headers, url)
        match = re.fullmatch(r"/odw/ID([0-9]+)Action\.action", urlparse(url).path)
        if match is None:
            raise AssertionError(f"unexpected Legislative Yuan endpoint: {url}")
        payload = self.responses.get(match.group(1), {"dataList": []})
        if isinstance(payload, Exception):
            raise payload
        headers = {} if self.content_type is None else {"Content-Type": self.content_type}
        return HttpResponse(
            200,
            json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers,
            url,
        )


def _metadata() -> PublicLawServerMetadata:
    return PublicLawServerMetadata(
        provider_id="official_legislative_yuan",
        snapshot_id="snapshot-ly-1",
        generation="generation-ly-1",
        receipt_id="receipt-ly-1",
        issued_at=NOW,
        expires_at=NOW + timedelta(hours=1),
    )


def _query(**overrides: Any) -> HistoricalLawQuery:
    values: dict[str, Any] = {
        "query_id": "ly-query-1",
        "law_name": "公司法",
        "bill_no": "BILL-001",
        "term": "11",
        "session": "03",
        "as_of_date": date(2026, 8, 20),
        "bounded_scope": "official-legislative-yuan-fixture",
        "max_results": 20,
    }
    values.update(overrides)
    return HistoricalLawQuery(**values)


def _row(dataset_id: str, *, bill_no: str = "BILL-001", **extra: Any) -> dict[str, Any]:
    if dataset_id == LEGISLATIVE_YUAN_PROPOSAL_DATASET:
        row: dict[str, Any] = {
            "term": "11",
            "sessionPeriod": "03",
            "sessionTimes": "01",
            "meetingTimes": "",
            "billNo": bill_no,
            "billName": "公司法部分條文修正草案",
            "billOrg": "司法及法制委員會",
            "billProposer": "測試委員",
            "billCosignatory": "",
            "billStatus": "審查完畢",
            "pdfUrl": "https://ppg.ly.gov.tw/ppg/download/proposal.pdf",
            "docUrl": "https://ppg.ly.gov.tw/ppg/download/proposal.doc",
        }
    elif dataset_id == LEGISLATIVE_YUAN_ARTICLE_COMPARISON_DATASET:
        row = {
            "term": "11",
            "sessionPeriod": "03",
            "sessionTimes": "01",
            "meetingTimes": "",
            "billNo": bill_no,
            "docNo": "院總第123號",
            "docUrl": "https://ppg.ly.gov.tw/ppg/download/compare.doc",
            "lawCompareTitle": "公司法條文對照表",
            "reviseLaw": "修正條文內容",
            "activeLaw": "現行條文內容",
            "description": "條文修正說明",
        }
    elif dataset_id == LEGISLATIVE_YUAN_COMMITTEE_DATASET:
        row = {
            "term": "11",
            "sessionPeriod": "03",
            "meetingNo": "M-001",
            "billNo": bill_no,
        }
    elif dataset_id == LEGISLATIVE_YUAN_CAUCUS_DATASET:
        row = {
            "comYear": "115",
            "comVolume": "1",
            "comBookId": "一",
            "term": "11",
            "sessionPeriod": "03",
            "sessionTimes": "01",
            "meetingTimes": "",
            "meetingDate": "115/05/01",
            "meetingName": "黨團協商會議",
            "subject": "公司法部分條文修正草案黨團協商",
            "docUrl": "https://ppg.ly.gov.tw/ppg/download/caucus.doc",
        }
    else:
        row = {
            "comYear": "115",
            "comVolume": "1",
            "comBookId": "一",
            "term": "11",
            "sessionPeriod": "03",
            "sessionTimes": "01",
            "meetingTimes": "",
            "meetingDate": "115/05/01",
            "meetingName": "立法院第11屆第3會期院會",
            "subject": "公司法部分條文修正草案三讀通過",
            "pdfUrl": "https://ppg.ly.gov.tw/ppg/download/third.pdf",
        }
    row.update(extra)
    return row


def _responses(*, bills: tuple[str, ...] = ("BILL-001",)) -> dict[str, object]:
    responses: dict[str, object] = {}
    for dataset_id in DATASET_IDS:
        row_bills = (
            bills
            if dataset_id
            not in {
                LEGISLATIVE_YUAN_CAUCUS_DATASET,
                LEGISLATIVE_YUAN_THIRD_READING_DATASET,
            }
            else bills[:1]
        )
        responses[dataset_id] = {
            "dataList": [_row(dataset_id, bill_no=bill_no) for bill_no in row_bills]
        }
    return responses


def _adapter(transport: FixtureTransport, **kwargs: Any) -> LegislativeYuanProviderAdapter:
    return LegislativeYuanProviderAdapter(
        transport=transport,
        metadata_issuer=lambda _provider, _request: _metadata(),
        **kwargs,
    )


def test_actual_fields_keep_locator_and_content_roles_separate() -> None:
    resolution = _adapter(FixtureTransport(_responses())).search(_query())

    assert resolution.provider_result.status is PublicLawResultStatus.PARTIAL
    assert not resolution.provider_result.coverage_complete
    assert not resolution.provider_result.absence_claim_allowed
    assert not resolution.normative_source_ids
    by_dataset = {
        str(record.metadata["dataset_id"]): record for record in resolution.legislative_records
    }
    assert set(by_dataset) == set(DATASET_IDS)

    proposal = by_dataset[LEGISLATIVE_YUAN_PROPOSAL_DATASET]
    assert proposal.role is LegislativeMaterialRole.PROPOSAL_DOCUMENT
    assert proposal.stage is LegislativeStage.PROPOSAL
    assert proposal.text is None
    assert proposal.metadata["locator_only"] is True
    assert proposal.metadata["structured_dataset_text_present"] is False
    assert proposal.metadata["linked_document_fetched"] is False

    comparison = by_dataset[LEGISLATIVE_YUAN_ARTICLE_COMPARISON_DATASET]
    assert comparison.role is LegislativeMaterialRole.ARTICLE_COMPARISON
    assert comparison.stage is LegislativeStage.SECOND_READING
    assert comparison.metadata["locator_only"] is False
    assert comparison.metadata["structured_dataset_text_present"] is True
    assert comparison.metadata["linked_document_fetched"] is False
    assert comparison.text is not None
    assert "reviseLaw: 修正條文內容" in comparison.text
    assert "activeLaw: 現行條文內容" in comparison.text
    assert "description: 條文修正說明" in comparison.text

    committee = by_dataset[LEGISLATIVE_YUAN_COMMITTEE_DATASET]
    assert committee.role is LegislativeMaterialRole.COMMITTEE_BILL
    assert committee.text is None
    assert committee.metadata["locator_only"] is True

    caucus = by_dataset[LEGISLATIVE_YUAN_CAUCUS_DATASET]
    assert caucus.role is LegislativeMaterialRole.CAUCUS_RECORD
    assert caucus.text is None
    assert caucus.document_date == date(2026, 5, 1)

    third_reading = by_dataset[LEGISLATIVE_YUAN_THIRD_READING_DATASET]
    assert third_reading.role is LegislativeMaterialRole.THIRD_READING_RECORD
    assert third_reading.text is None
    assert third_reading.document_date == date(2026, 5, 1)

    assert all(record.candidate_only for record in resolution.legislative_records)
    assert all(
        record.metadata["linked_document_fetched"] is False
        and "document_text_retrieved" not in record.metadata
        for record in resolution.legislative_records
    )
    assert all(record.locator_url is not None for record in resolution.legislative_records)
    assert all(
        candidate.material_type.value == "legislative_material"
        for candidate in resolution.provider_result.candidates
    )
    assert "HISTORICAL_LAW_NORMATIVE_SOURCE_MISSING" in resolution.warnings
    assert "HISTORICAL_LAW_PROMULGATED_VERSION_MISSING" in resolution.warnings

    validation = validate_historical_law_resolution(
        resolution,
        server_metadata=_metadata(),
        server_source_ids=[],
        now=NOW,
    )
    assert validation.decision is PublicLawValidationDecision.QUALIFIED


def test_targeted_endpoint_query_mapping_uses_documented_parameters() -> None:
    transport = FixtureTransport(_responses())
    _adapter(transport).search(_query(law_name="個人資料保護法"))

    assert len(transport.calls) == len(DATASET_IDS)
    calls: dict[str, dict[str, list[str]]] = {}
    for url, timeout, max_bytes in transport.calls:
        parsed = urlparse(url)
        match = re.fullmatch(r"/odw/ID([0-9]+)Action\.action", parsed.path)
        assert match is not None
        dataset_id = match.group(1)
        calls[dataset_id] = parse_qs(parsed.query, keep_blank_values=True)
        assert parsed.scheme == "https"
        assert parsed.hostname == "data.ly.gov.tw"
        assert timeout <= 30
        assert max_bytes <= 4 * 1024 * 1024
        assert "openDatasetJson.action" not in url
        assert "id" not in calls[dataset_id]
        assert "selectTerm" not in calls[dataset_id]
        assert "page" not in calls[dataset_id]
        assert calls[dataset_id]["fileType"] == ["json"]
        assert calls[dataset_id]["term"] == ["11"]
        assert calls[dataset_id]["sessionPeriod"] == ["03"]

    assert set(calls) == set(DATASET_IDS)
    assert not set(LEGISLATIVE_YUAN_UNSUPPORTED_DATASET_IDS) & set(calls)
    assert calls[LEGISLATIVE_YUAN_PROPOSAL_DATASET]["billName"] == ["個人資料保護法"]
    for dataset_id in (
        LEGISLATIVE_YUAN_CAUCUS_DATASET,
        LEGISLATIVE_YUAN_THIRD_READING_DATASET,
    ):
        assert calls[dataset_id]["meetingDateS"] == [""]
        assert calls[dataset_id]["meetingDateE"] == ["115/08/20"]


def test_fabricated_content_and_promulgated_fields_are_ignored() -> None:
    responses = _responses()
    responses[LEGISLATIVE_YUAN_PROPOSAL_DATASET] = {
        "dataList": [
            _row(
                LEGISLATIVE_YUAN_PROPOSAL_DATASET,
                proposalReason="fabricated proposal text",
                promulgatedUrl="https://lis.ly.gov.tw/lglawc/fabricated",
            )
        ]
    }
    responses[LEGISLATIVE_YUAN_COMMITTEE_DATASET] = {
        "dataList": [
            _row(
                LEGISLATIVE_YUAN_COMMITTEE_DATASET,
                committeeReport="fabricated committee text",
            )
        ]
    }
    responses[LEGISLATIVE_YUAN_THIRD_READING_DATASET] = {
        "dataList": [
            _row(
                LEGISLATIVE_YUAN_THIRD_READING_DATASET,
                thirdReadingText="fabricated third-reading text",
                promulgatedUrl="https://lis.ly.gov.tw/lglawc/fabricated",
            )
        ]
    }
    resolution = _adapter(FixtureTransport(responses)).search(_query())

    forbidden_roles = {
        LegislativeMaterialRole.PROPOSAL_REASON,
        LegislativeMaterialRole.COMMITTEE_REPORT,
        LegislativeMaterialRole.THIRD_READING_TEXT,
        LegislativeMaterialRole.PROMULGATED_VERSION_LINK,
    }
    assert forbidden_roles.isdisjoint({record.role for record in resolution.legislative_records})
    locator_roles = {
        LegislativeMaterialRole.PROPOSAL_DOCUMENT,
        LegislativeMaterialRole.COMMITTEE_BILL,
        LegislativeMaterialRole.THIRD_READING_RECORD,
    }
    assert all(
        record.text is None
        for record in resolution.legislative_records
        if record.role in locator_roles
    )
    assert all(
        "fabricated" not in (candidate.official_url or "")
        for candidate in resolution.provider_result.candidates
    )
    assert not resolution.normative_source_ids


def test_multiple_bills_are_bounded_and_preserve_bill_linkage() -> None:
    transport = FixtureTransport(_responses(bills=("BILL-001", "BILL-002")))
    resolution = _adapter(transport, max_results=20).search(_query(bill_no=None))

    assert {
        record.bill_no for record in resolution.legislative_records if record.bill_no is not None
    } == {
        "BILL-001",
        "BILL-002",
    }
    assert all(
        record.bill_no is None
        for record in resolution.legislative_records
        if record.role
        in {
            LegislativeMaterialRole.CAUCUS_RECORD,
            LegislativeMaterialRole.THIRD_READING_RECORD,
        }
    )
    assert all(
        record.term == "11" and record.session == "03" for record in resolution.legislative_records
    )


@pytest.mark.parametrize(
    ("term", "session"),
    [("11", "3"), ("011", "03")],
)
def test_zero_padded_term_and_session_are_equivalent(term: str, session: str) -> None:
    resolution = _adapter(FixtureTransport(_responses())).search(_query(term=term, session=session))

    assert resolution.provider_result.status is PublicLawResultStatus.PARTIAL
    assert resolution.legislative_records
    assert "HISTORICAL_LAW_SOURCE_ROLE_INVALID" not in resolution.warnings
    assert all(
        record.term == "11" and record.session == "03" for record in resolution.legislative_records
    )


def test_missing_final_version_is_explicitly_qualified() -> None:
    transport = FixtureTransport(_responses())
    resolution = _adapter(transport).search(_query())

    assert "HISTORICAL_LAW_PROMULGATED_VERSION_MISSING" in resolution.warnings
    assert "HISTORICAL_LAW_NORMATIVE_SOURCE_MISSING" in resolution.warnings
    assert resolution.provider_result.status is PublicLawResultStatus.PARTIAL
    assert LegislativeMaterialRole.PROMULGATED_VERSION_LINK not in {
        record.role for record in resolution.legislative_records
    }
    assert resolution.provider_result.metadata["normative_provider_required"] is True
    assert resolution.provider_result.metadata["promulgated_version_synthesized"] is False


def test_as_of_date_excludes_later_rows_and_marks_undated_rows_partial() -> None:
    responses = _responses()
    responses[LEGISLATIVE_YUAN_CAUCUS_DATASET] = {
        "dataList": [_row(LEGISLATIVE_YUAN_CAUCUS_DATASET, meetingDate="116/01/01")]
    }
    resolution = _adapter(FixtureTransport(responses)).search(_query())

    assert all(
        record.role is not LegislativeMaterialRole.CAUCUS_RECORD
        for record in resolution.legislative_records
    )
    assert resolution.provider_result.status is PublicLawResultStatus.PARTIAL
    assert not resolution.provider_result.coverage_complete
    assert "LEGISLATIVE_YUAN_AFTER_AS_OF_EXCLUDED:8" in (resolution.provider_result.reason_codes)
    assert "LEGISLATIVE_YUAN_AS_OF_DATE_UNVERIFIED:20" in (resolution.provider_result.reason_codes)
    assert resolution.provider_result.metadata["excluded_after_as_of_count"] == 1


def test_multi_date_record_uses_latest_date_for_as_of_exclusion() -> None:
    responses = _responses()
    responses[LEGISLATIVE_YUAN_CAUCUS_DATASET] = {
        "dataList": [
            _row(
                LEGISLATIVE_YUAN_CAUCUS_DATASET,
                meetingDate="115/05/01,116/01/01",
            )
        ]
    }

    resolution = _adapter(FixtureTransport(responses)).search(_query())

    assert all(
        record.role is not LegislativeMaterialRole.CAUCUS_RECORD
        for record in resolution.legislative_records
    )
    assert "LEGISLATIVE_YUAN_AFTER_AS_OF_EXCLUDED:8" in resolution.provider_result.reason_codes


def test_candidate_ids_are_deterministic_and_do_not_collide_across_terms() -> None:
    first = _adapter(FixtureTransport(_responses())).search(_query())
    repeated = _adapter(FixtureTransport(_responses())).search(_query())
    next_term_responses = {
        dataset_id: {
            "dataList": [
                _row(
                    dataset_id,
                    term="12",
                    sessionPeriod="01",
                    meetingDate="116/05/01",
                )
            ]
        }
        for dataset_id in DATASET_IDS
    }
    next_term = _adapter(FixtureTransport(next_term_responses)).search(
        _query(term="12", session="01", as_of_date=date(2027, 8, 20))
    )

    first_ids = {item.candidate_id for item in first.provider_result.candidates}
    repeated_ids = {item.candidate_id for item in repeated.provider_result.candidates}
    next_term_ids = {item.candidate_id for item in next_term.provider_result.candidates}
    assert first_ids == repeated_ids
    assert first_ids.isdisjoint(next_term_ids)
    assert all(len(candidate_id) <= 80 for candidate_id in first_ids | next_term_ids)


def test_duplicate_official_rows_are_deduplicated_and_mark_coverage_partial() -> None:
    responses = _responses()
    duplicate = _row(LEGISLATIVE_YUAN_PROPOSAL_DATASET)
    responses[LEGISLATIVE_YUAN_PROPOSAL_DATASET] = {"dataList": [duplicate, dict(duplicate)]}

    resolution = _adapter(FixtureTransport(responses)).search(_query())
    candidate_ids = [candidate.candidate_id for candidate in resolution.provider_result.candidates]
    proposal_records = [
        record
        for record in resolution.legislative_records
        if record.role is LegislativeMaterialRole.PROPOSAL_DOCUMENT
    ]

    assert len(candidate_ids) == len(set(candidate_ids))
    assert len(proposal_records) == 1
    assert resolution.provider_result.status is PublicLawResultStatus.PARTIAL
    assert not resolution.provider_result.coverage_complete
    assert "LEGISLATIVE_YUAN_DUPLICATE_ROW:20" in (resolution.provider_result.reason_codes)
    assert resolution.provider_result.metadata["duplicate_candidate_count"] == 1
    coverage = json.loads(str(resolution.provider_result.metadata["dataset_coverage_json"]))
    assert coverage[LEGISLATIVE_YUAN_PROPOSAL_DATASET]["duplicate_rows"] == 1


def test_empty_data_never_overstates_scope_or_temporal_absence() -> None:
    scoped = _adapter(FixtureTransport()).search(_query())
    assert scoped.provider_result.status is PublicLawResultStatus.PARTIAL
    assert not scoped.provider_result.coverage_complete
    assert not scoped.provider_result.absence_claim_allowed
    assert "LEGISLATIVE_YUAN_AS_OF_DATE_UNVERIFIED:20" in (scoped.provider_result.reason_codes)
    assert scoped.provider_result.metadata["scope_term"] == "11"
    assert scoped.provider_result.metadata["scope_session"] == "03"
    assert scoped.provider_result.metadata["absence_scope_authoritative"] is False
    coverage = json.loads(str(scoped.provider_result.metadata["dataset_coverage_json"]))
    assert set(coverage) == set(DATASET_IDS)

    unscoped_transport = FixtureTransport()
    unscoped = _adapter(unscoped_transport).search(
        _query(
            bill_no=None,
            term=None,
            session=None,
            bounded_scope="caller claims all legislative history",
        )
    )
    assert unscoped.provider_result.status is PublicLawResultStatus.PARTIAL
    assert not unscoped.provider_result.absence_claim_allowed
    assert "LEGISLATIVE_YUAN_TERM_SCOPE_REQUIRED" in (unscoped.provider_result.reason_codes)
    assert "term=unspecified" in str(unscoped.provider_result.metadata["effective_scope"])
    assert [urlparse(call[0]).path for call in unscoped_transport.calls] == [
        "/odw/ID20Action.action"
    ]
    assert unscoped.provider_result.metadata["queried_dataset_ids"] == "20"
    for dataset_id in ("19", "46", "8", "48"):
        assert f"LEGISLATIVE_YUAN_DATASET_SCOPE_REQUIRED:{dataset_id}" in (
            unscoped.provider_result.reason_codes
        )

    term_only_transport = FixtureTransport()
    term_only = _adapter(term_only_transport).search(_query(bill_no=None, session=None))
    assert "LEGISLATIVE_YUAN_SESSION_SCOPE_REQUIRED" in (term_only.provider_result.reason_codes)
    assert [urlparse(call[0]).path for call in term_only_transport.calls] == [
        "/odw/ID20Action.action"
    ]

    identifier_transport = FixtureTransport()
    identifier_only = _adapter(identifier_transport).search(
        _query(
            law_name=None,
            law_identifier="1234567890",
            bill_no=None,
            term=None,
            session=None,
        )
    )
    assert identifier_only.provider_result.status is PublicLawResultStatus.PARTIAL
    assert not identifier_transport.calls


def test_malformed_json_and_shape_are_retry_required_not_not_found() -> None:
    malformed = FixtureTransport(raw_content=b"not-json")
    backend_result = LegislativeYuanDataBackend(transport=malformed).search(_query())
    assert backend_result.status == "error"
    assert any("DATASET_ERROR" in reason for reason in backend_result.reason_codes)

    shaped = FixtureTransport(
        responses={dataset_id: {"jsonList": []} for dataset_id in DATASET_IDS}
    )
    result = _adapter(shaped).search(_query()).provider_result
    assert result.status is PublicLawResultStatus.RETRY_REQUIRED
    assert result.status is not PublicLawResultStatus.NOT_FOUND_IN_SCOPE

    malformed_rows = FixtureTransport(
        responses={dataset_id: {"dataList": ["not-an-object"]} for dataset_id in DATASET_IDS}
    )
    assert (
        _adapter(malformed_rows).search(_query()).provider_result.status
        is PublicLawResultStatus.RETRY_REQUIRED
    )


def test_oversize_and_timeout_fail_closed() -> None:
    oversize = FixtureTransport(raw_content=b'{"dataList": []}')
    oversize_result = LegislativeYuanDataBackend(
        transport=oversize,
        max_response_bytes=10,
    ).search(_query())
    assert oversize_result.status == "error"
    assert all("DATASET_ERROR" in reason for reason in oversize_result.reason_codes)

    timeout = FixtureTransport(error=TimeoutError("fixture timeout"))
    timeout_result = _adapter(timeout).search(_query()).provider_result
    assert timeout_result.status is PublicLawResultStatus.RETRY_REQUIRED


def test_content_type_allows_official_text_plain_but_rejects_missing_header() -> None:
    text_plain = FixtureTransport(
        _responses(),
        content_type="text/plain;charset=UTF-8",
    )
    assert _adapter(text_plain).search(_query()).provider_result.candidates

    missing = FixtureTransport(_responses(), content_type=None)
    result = _adapter(missing).search(_query()).provider_result
    assert result.status is PublicLawResultStatus.RETRY_REQUIRED
    assert not result.candidates


def test_redirect_and_malicious_payload_locator_are_rejected() -> None:
    redirected = FixtureTransport(redirect_url="https://evil.example/redirect")
    result = _adapter(redirected).search(_query()).provider_result
    assert result.status is PublicLawResultStatus.RETRY_REQUIRED
    assert not result.candidates

    malicious = _responses()
    malicious[LEGISLATIVE_YUAN_PROPOSAL_DATASET] = {
        "dataList": [
            _row(
                LEGISLATIVE_YUAN_PROPOSAL_DATASET,
                pdfUrl="https://evil.example/x.pdf",
            )
        ]
    }
    rejected = _adapter(FixtureTransport(malicious)).search(_query()).provider_result
    assert rejected.status is PublicLawResultStatus.PARTIAL
    assert rejected.candidates
    assert all(
        "evil.example" not in (candidate.official_url or "") for candidate in rejected.candidates
    )


@pytest.mark.parametrize(
    "url",
    [
        "http://data.ly.gov.tw/odw/ID20Action.action?fileType=json",
        "https://evil.example/official",
        "https://data.ly.gov.tw:8443/official",
        "https://data.ly.gov.tw/official#fragment",
        "https://user:pass@data.ly.gov.tw/official",
        "https://ppg.ly.gov.tw/ppg/download/proposal.pdf",
    ],
)
def test_malicious_urls_are_not_accepted_by_http_client(url: str) -> None:
    with pytest.raises(ValueError, match="LEGISLATIVE_YUAN_URL_INVALID"):
        LegislativeYuanHttpClient.validate_url(url)

    assert "data.ly.gov.tw" in LEGISLATIVE_YUAN_ALLOWED_HOSTS
    assert LEGISLATIVE_YUAN_DATA_HOST == "data.ly.gov.tw"


def test_official_tls_compatibility_keeps_peer_verification_and_blocks_renegotiation() -> None:
    context = _official_ssl_context()

    assert context.check_hostname is True
    assert context.verify_mode is ssl.CERT_REQUIRED
    if hasattr(ssl, "OP_LEGACY_SERVER_CONNECT"):
        assert context.options & ssl.OP_LEGACY_SERVER_CONNECT
    if hasattr(ssl, "OP_NO_RENEGOTIATION"):
        assert context.options & ssl.OP_NO_RENEGOTIATION


def test_result_bound_is_visible() -> None:
    bounded = FixtureTransport(_responses(bills=("BILL-001", "BILL-002")))
    result = (
        _adapter(bounded, max_results=2).search(_query(bill_no=None, max_results=2)).provider_result
    )
    assert len(result.candidates) == 2
    assert result.truncated
    assert result.status is PublicLawResultStatus.PARTIAL
    assert "PUBLIC_LAW_RESULT_LIMIT_TRUNCATED" in result.reason_codes


def test_page_bound_marks_full_page_as_partial() -> None:
    responses = {
        LEGISLATIVE_YUAN_PROPOSAL_DATASET: {
            "dataList": [
                _row(
                    LEGISLATIVE_YUAN_PROPOSAL_DATASET,
                    bill_no=f"BILL-{index:04}",
                )
                for index in range(DATASET_PAGE_SIZE)
            ]
        }
    }
    backend = LegislativeYuanDataBackend(
        transport=FixtureTransport(responses),
        max_pages=1,
        max_results=2,
    )
    result = backend.search(_query(max_results=2))
    assert result.status == "partial"
    assert not result.coverage_complete
    assert "LEGISLATIVE_YUAN_DATASET_ROW_LIMIT:20" in result.reason_codes

    with pytest.raises(ValueError, match="LEGISLATIVE_YUAN_PAGE_LIMIT_INVALID"):
        LegislativeYuanDataBackend(transport=FixtureTransport(), max_pages=2)


def test_adapter_without_server_metadata_is_blocked() -> None:
    result = (
        LegislativeYuanProviderAdapter(
            transport=FixtureTransport(_responses()),
        )
        .search(_query())
        .provider_result
    )
    assert result.status is PublicLawResultStatus.BLOCKED
