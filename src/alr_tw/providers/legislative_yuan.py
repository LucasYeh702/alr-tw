"""Optional, read-only Legislative Yuan open-data connector.

The connector uses the official ``data.ly.gov.tw`` JSON dataset endpoint as a
bounded locator source.  Proposal, article-comparison, committee, caucus and
third-reading datasets carry different roles and are never merged into a
normative law source.  Linked PDF/DOC files are retained as locators only;
this module does not parse them.

The backend deliberately returns candidate records.  The existing
``LegislativeHistoryProviderAdapter`` still requires the server-owned
metadata issuer and source promoter before any source can become evidence.
"""

from __future__ import annotations

import hashlib
import json
import re
import socket
import ssl
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Protocol

from alr_tw.contracts.historical_law import (
    HistoricalLawQuery,
    LegislativeHistoryRecord,
    LegislativeMaterialRole,
    LegislativeStage,
)
from alr_tw.contracts.public_law import (
    PublicLawCandidate,
    PublicLawMaterialType,
    PublicLawSourceRole,
)
from alr_tw.providers.official.http import HttpResponse
from alr_tw.providers.sdk import (
    PublicLawBackendResult,
    PublicLawBackendStatus,
    PublicLawMetadataIssuer,
    PublicLawSourcePromoter,
)

from .legislative_history import (
    LegislativeHistoryBackend,
    LegislativeHistoryProviderAdapter,
)


LEGISLATIVE_YUAN_PROVIDER_ID = "official_legislative_yuan"
LEGISLATIVE_YUAN_DATA_ORIGIN = "https://data.ly.gov.tw"
LEGISLATIVE_YUAN_DATA_HOST = "data.ly.gov.tw"
LEGISLATIVE_YUAN_ALLOWED_HOSTS = frozenset(
    {LEGISLATIVE_YUAN_DATA_HOST, "ppg.ly.gov.tw", "lis.ly.gov.tw"}
)
LEGISLATIVE_YUAN_DATASET_PATH_TEMPLATE = "/odw/ID{dataset_id}Action.action"

# Dataset IDs and their official catalog roles.  These are locators only;
# the endpoint does not imply that a linked document was fetched or parsed.
LEGISLATIVE_YUAN_PROPOSAL_DATASET = "20"
LEGISLATIVE_YUAN_ARTICLE_COMPARISON_DATASET = "19"
LEGISLATIVE_YUAN_COMMITTEE_DATASET = "46"
LEGISLATIVE_YUAN_CAUCUS_DATASET = "8"
LEGISLATIVE_YUAN_THIRD_READING_DATASET = "48"
LEGISLATIVE_YUAN_UNSUPPORTED_DATASET_IDS = ("373",)

MAX_TIMEOUT_SECONDS = 30.0
MAX_RESPONSE_BYTES = 4 * 1024 * 1024
MAX_PAGES = 1
MAX_RESULTS = 50
DATASET_PAGE_SIZE = 1000


class LegislativeYuanHttpTransport(Protocol):
    """Injectable synchronous HTTP boundary used by the read-only backend."""

    def get(self, url: str, *, timeout: float, max_bytes: int) -> HttpResponse: ...


class LegislativeYuanHttpClient:
    """Stdlib HTTPS client with no redirects and a response-byte bound.

    The fixed official data host currently lacks RFC 5746 secure-renegotiation
    support.  On Python/OpenSSL versions that expose the client-only
    compatibility flag, the context permits the initial connection while
    keeping CA/hostname verification enabled and disabling renegotiation after
    the handshake.
    """

    def __init__(
        self,
        *,
        user_agent: str = "Mozilla/5.0 ALR-TW-Legislative-Yuan/0.10",
    ) -> None:
        self.user_agent = user_agent
        self._opener = urllib.request.build_opener(
            _RejectRedirectHandler(),
            urllib.request.HTTPSHandler(context=_official_ssl_context()),
        )

    @staticmethod
    def validate_url(url: str) -> None:
        try:
            parsed = urllib.parse.urlparse(url)
            port = parsed.port
        except ValueError as exc:
            raise ValueError("LEGISLATIVE_YUAN_URL_INVALID") from exc
        if (
            parsed.scheme != "https"
            or parsed.hostname is None
            or parsed.hostname.lower() != LEGISLATIVE_YUAN_DATA_HOST
            or parsed.username is not None
            or parsed.password is not None
            or port not in {None, 443}
            or parsed.fragment
        ):
            raise ValueError("LEGISLATIVE_YUAN_URL_INVALID")

    def get(self, url: str, *, timeout: float, max_bytes: int) -> HttpResponse:
        if timeout <= 0 or timeout > MAX_TIMEOUT_SECONDS:
            raise ValueError("LEGISLATIVE_YUAN_TIMEOUT_LIMIT_INVALID")
        if max_bytes <= 0 or max_bytes > MAX_RESPONSE_BYTES:
            raise ValueError("LEGISLATIVE_YUAN_RESPONSE_LIMIT_INVALID")
        self.validate_url(url)
        request = urllib.request.Request(
            url,
            headers={
                "Accept": "application/json",
                "User-Agent": self.user_agent,
            },
            method="GET",
        )
        try:
            with self._opener.open(request, timeout=timeout) as response:
                final_url = str(response.geturl())
                status_code = int(getattr(response, "status", 0) or 0)
                headers = dict(response.headers.items())
                content = response.read(max_bytes + 1)
        except ValueError:
            raise
        except (urllib.error.URLError, OSError, socket.timeout) as exc:
            raise RuntimeError("LEGISLATIVE_YUAN_HTTP_FAILED") from exc
        if final_url != url:
            raise RuntimeError("LEGISLATIVE_YUAN_REDIRECT_NOT_ALLOWED")
        return HttpResponse(status_code, content, headers, final_url)


@dataclass(frozen=True, slots=True)
class _DatasetDefinition:
    dataset_id: str
    role: LegislativeMaterialRole
    stage: LegislativeStage
    query_fields: tuple[str, ...]
    title_fields: tuple[str, ...]
    locator_fields: tuple[str, ...]
    text_fields: tuple[str, ...] = ()
    date_fields: tuple[str, ...] = ()


_DATASETS = (
    _DatasetDefinition(
        LEGISLATIVE_YUAN_PROPOSAL_DATASET,
        LegislativeMaterialRole.PROPOSAL_DOCUMENT,
        LegislativeStage.PROPOSAL,
        (
            "term",
            "sessionPeriod",
            "sessionTimes",
            "meetingTimes",
            "billName",
            "billOrg",
            "billProposer",
            "billCosignatory",
        ),
        ("billName",),
        ("pdfUrl", "docUrl"),
    ),
    _DatasetDefinition(
        LEGISLATIVE_YUAN_ARTICLE_COMPARISON_DATASET,
        LegislativeMaterialRole.ARTICLE_COMPARISON,
        LegislativeStage.SECOND_READING,
        ("term", "sessionPeriod", "sessionTimes", "meetingTimes"),
        ("lawCompareTitle",),
        ("docUrl",),
        ("reviseLaw", "activeLaw", "description"),
    ),
    _DatasetDefinition(
        LEGISLATIVE_YUAN_COMMITTEE_DATASET,
        LegislativeMaterialRole.COMMITTEE_BILL,
        LegislativeStage.COMMITTEE_REVIEW,
        ("term", "sessionPeriod", "sessionTimes", "meetingTimes"),
        ("meetingNo",),
        (),
    ),
    _DatasetDefinition(
        LEGISLATIVE_YUAN_CAUCUS_DATASET,
        LegislativeMaterialRole.CAUCUS_RECORD,
        LegislativeStage.CAUCUS,
        (
            "comYear",
            "comVolume",
            "comBookId",
            "term",
            "sessionPeriod",
            "sessionTimes",
            "meetingTimes",
            "meetingDateS",
            "meetingDateE",
        ),
        ("subject", "meetingName"),
        ("docUrl",),
        (),
        ("meetingDate",),
    ),
    _DatasetDefinition(
        LEGISLATIVE_YUAN_THIRD_READING_DATASET,
        LegislativeMaterialRole.THIRD_READING_RECORD,
        LegislativeStage.THIRD_READING,
        (
            "comYear",
            "comVolume",
            "comBookId",
            "term",
            "sessionPeriod",
            "sessionTimes",
            "meetingTimes",
            "meetingDateS",
            "meetingDateE",
        ),
        ("subject", "meetingName"),
        ("pdfUrl",),
        (),
        ("meetingDate",),
    ),
)

_BILL_FIELDS = ("billNo", "bill_no", "議案編號")
_TERM_FIELDS = ("term", "屆別")
_SESSION_FIELDS = ("sessionPeriod", "session", "會期")


class LegislativeYuanDataBackend(LegislativeHistoryBackend):
    """Bounded backend over official Legislative Yuan JSON datasets."""

    provider_id = LEGISLATIVE_YUAN_PROVIDER_ID

    def __init__(
        self,
        transport: LegislativeYuanHttpTransport | None = None,
        *,
        base_url: str = LEGISLATIVE_YUAN_DATA_ORIGIN,
        timeout_seconds: float = 15.0,
        max_response_bytes: int = MAX_RESPONSE_BYTES,
        max_pages: int = 1,
        max_results: int = 20,
    ) -> None:
        self._origin = self._validate_base_url(base_url)
        if timeout_seconds <= 0 or timeout_seconds > MAX_TIMEOUT_SECONDS:
            raise ValueError("LEGISLATIVE_YUAN_TIMEOUT_LIMIT_INVALID")
        if max_response_bytes <= 0 or max_response_bytes > MAX_RESPONSE_BYTES:
            raise ValueError("LEGISLATIVE_YUAN_RESPONSE_LIMIT_INVALID")
        if max_pages != MAX_PAGES:
            raise ValueError("LEGISLATIVE_YUAN_PAGE_LIMIT_INVALID")
        if max_results <= 0 or max_results > MAX_RESULTS:
            raise ValueError("LEGISLATIVE_YUAN_RESULT_LIMIT_INVALID")
        self.timeout_seconds = float(timeout_seconds)
        self.max_response_bytes = int(max_response_bytes)
        self.max_pages = int(max_pages)
        self.max_results = int(max_results)
        self._transport = transport or LegislativeYuanHttpClient()

    @staticmethod
    def _validate_base_url(value: str) -> str:
        try:
            parsed = urllib.parse.urlparse(str(value).rstrip("/"))
            port = parsed.port
        except ValueError as exc:
            raise ValueError("LEGISLATIVE_YUAN_BASE_URL_INVALID") from exc
        if (
            parsed.scheme != "https"
            or parsed.hostname is None
            or parsed.hostname.lower() != "data.ly.gov.tw"
            or parsed.username is not None
            or parsed.password is not None
            or port not in {None, 443}
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("LEGISLATIVE_YUAN_BASE_URL_INVALID")
        return "https://data.ly.gov.tw"

    def search(self, request: HistoricalLawQuery) -> PublicLawBackendResult:
        if not request.include_legislative_history:
            return PublicLawBackendResult(
                provider_id=self.provider_id,
                query_id=request.query_id,
                status=PublicLawBackendStatus.NOT_FOUND,
                coverage_complete=True,
                metadata={"history_requested": False},
            )

        try:
            term, session = self._query_scope(request)
        except ValueError as exc:
            return PublicLawBackendResult(
                provider_id=self.provider_id,
                query_id=request.query_id,
                status=PublicLawBackendStatus.ERROR,
                reason_codes=[str(exc)],
            )
        candidates: list[PublicLawCandidate] = []
        reasons: list[str] = []
        scope_complete = bool(term and session)
        if not term:
            reasons.append("LEGISLATIVE_YUAN_TERM_SCOPE_REQUIRED")
        elif not session:
            reasons.append("LEGISLATIVE_YUAN_SESSION_SCOPE_REQUIRED")
        incomplete_dataset_ids: set[str] = set()
        failed_dataset_ids: set[str] = set()
        matched_count = 0
        result_limit_hit = False
        linked_bill_nos: set[str] = set()
        excluded_after_as_of_count = 0
        dataset_coverage: dict[str, dict[str, str | int | bool]] = {}
        law_name_filter = _law_name_filter(request)
        queried_dataset_ids: list[str] = []
        seen_candidate_ids: set[str] = set()
        duplicate_candidate_count = 0

        for dataset in _DATASETS:
            coverage: dict[str, str | int | bool] = {
                "term": term,
                "session": session,
                "as_of_date": request.as_of_date.isoformat(),
                "date_field_available": bool(dataset.date_fields),
                "duplicate_rows": 0,
            }
            dataset_coverage[dataset.dataset_id] = coverage
            if not scope_complete and (
                dataset.dataset_id != LEGISLATIVE_YUAN_PROPOSAL_DATASET or not law_name_filter
            ):
                incomplete_dataset_ids.add(dataset.dataset_id)
                coverage["fetch_skipped"] = True
                coverage["skip_reason"] = "dataset_scope_required"
                reasons.append(f"LEGISLATIVE_YUAN_DATASET_SCOPE_REQUIRED:{dataset.dataset_id}")
                continue
            queried_dataset_ids.append(dataset.dataset_id)
            try:
                rows, complete = self._fetch_dataset(dataset, request, term, session)
            except Exception as exc:
                failed_dataset_ids.add(dataset.dataset_id)
                incomplete_dataset_ids.add(dataset.dataset_id)
                coverage["fetch_complete"] = False
                reasons.append(
                    f"LEGISLATIVE_YUAN_DATASET_ERROR:{dataset.dataset_id}:{type(exc).__name__}"
                )
                continue
            coverage["fetch_complete"] = complete
            coverage["rows_received"] = len(rows)
            if not complete:
                incomplete_dataset_ids.add(dataset.dataset_id)
                reasons.append(f"LEGISLATIVE_YUAN_DATASET_ROW_LIMIT:{dataset.dataset_id}")
            dated_rows = 0
            undated_rows = 0
            excluded_rows = 0
            duplicate_rows = 0
            for ordinal, (row, endpoint_url) in enumerate(rows):
                try:
                    document_date = _parse_document_date(row, dataset.date_fields)
                    if document_date is None:
                        undated_rows += 1
                        incomplete_dataset_ids.add(dataset.dataset_id)
                        reasons.append(
                            f"LEGISLATIVE_YUAN_AS_OF_DATE_UNVERIFIED:{dataset.dataset_id}"
                        )
                    else:
                        dated_rows += 1
                        if document_date > request.as_of_date:
                            excluded_rows += 1
                            excluded_after_as_of_count += 1
                            reasons.append(
                                f"LEGISLATIVE_YUAN_AFTER_AS_OF_EXCLUDED:{dataset.dataset_id}"
                            )
                            continue
                    matches = self._row_matches(
                        dataset,
                        row,
                        request,
                        linked_bill_nos,
                    )
                except ValueError as exc:
                    incomplete_dataset_ids.add(dataset.dataset_id)
                    reasons.append(
                        f"LEGISLATIVE_YUAN_ROW_REJECTED:{dataset.dataset_id}:{type(exc).__name__}"
                    )
                    continue
                if not matches:
                    continue
                try:
                    row_candidates = self._row_candidates(
                        dataset,
                        row,
                        endpoint_url=endpoint_url,
                        ordinal=ordinal,
                        request=request,
                        document_date=document_date,
                    )
                except ValueError as exc:
                    reasons.append(
                        f"LEGISLATIVE_YUAN_ROW_REJECTED:{dataset.dataset_id}:{type(exc).__name__}"
                    )
                    continue
                matched_count += 1
                row_bill = _first_text(row, _BILL_FIELDS)
                if row_bill is not None:
                    linked_bill_nos.add(row_bill)
                for candidate in row_candidates:
                    if candidate.candidate_id in seen_candidate_ids:
                        duplicate_candidate_count += 1
                        duplicate_rows += 1
                        incomplete_dataset_ids.add(dataset.dataset_id)
                        reasons.append(f"LEGISLATIVE_YUAN_DUPLICATE_ROW:{dataset.dataset_id}")
                        continue
                    seen_candidate_ids.add(candidate.candidate_id)
                    if len(candidates) >= min(
                        request.max_results,
                        self.max_results,
                    ):
                        result_limit_hit = True
                        continue
                    candidates.append(candidate)
            coverage["dated_rows"] = dated_rows
            coverage["undated_rows"] = undated_rows
            coverage["excluded_after_as_of"] = excluded_rows
            coverage["duplicate_rows"] = duplicate_rows
            if not rows or not dataset.date_fields:
                incomplete_dataset_ids.add(dataset.dataset_id)
                reasons.append(f"LEGISLATIVE_YUAN_AS_OF_DATE_UNVERIFIED:{dataset.dataset_id}")

        reasons = list(dict.fromkeys(reasons))
        complete = not incomplete_dataset_ids and scope_complete
        result_truncated = result_limit_hit
        if result_truncated:
            reasons.append("PUBLIC_LAW_RESULT_LIMIT_TRUNCATED")
        if reasons and not candidates and len(failed_dataset_ids) == len(_DATASETS):
            status = PublicLawBackendStatus.ERROR
        elif candidates:
            status = (
                PublicLawBackendStatus.FOUND
                if complete and not reasons
                else PublicLawBackendStatus.PARTIAL
            )
        elif complete and not reasons:
            status = PublicLawBackendStatus.NOT_FOUND
        else:
            status = PublicLawBackendStatus.PARTIAL
        return PublicLawBackendResult(
            provider_id=self.provider_id,
            query_id=request.query_id,
            status=status,
            candidates=candidates,
            coverage_complete=complete and not reasons,
            truncated=result_truncated,
            reason_codes=reasons,
            metadata={
                "dataset_count": len(_DATASETS),
                "active_dataset_ids": ",".join(dataset.dataset_id for dataset in _DATASETS),
                "queried_dataset_ids": ",".join(queried_dataset_ids),
                "matched_count": matched_count,
                "unique_matched_candidate_count": len(seen_candidate_ids),
                "duplicate_candidate_count": duplicate_candidate_count,
                "failed_dataset_count": len(failed_dataset_ids),
                "incomplete_dataset_count": len(incomplete_dataset_ids),
                "excluded_after_as_of_count": excluded_after_as_of_count,
                "linked_documents_locator_only": True,
                "pdf_doc_parsing": False,
                "normative_provider_required": True,
                "promulgated_version_synthesized": False,
                "scope_term": term or None,
                "scope_session": session or None,
                "scope_as_of_date": request.as_of_date.isoformat(),
                "effective_scope": (
                    "datasets=20,19,46,8,48;"
                    f"term={term or 'unspecified'};"
                    f"session={session or 'unspecified'};"
                    f"as_of={request.as_of_date.isoformat()}"
                ),
                "absence_scope_authoritative": False,
                "dataset_coverage_json": json.dumps(
                    dataset_coverage,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                "unsupported_dataset_ids": ",".join(LEGISLATIVE_YUAN_UNSUPPORTED_DATASET_IDS),
            },
        )

    def _fetch_dataset(
        self,
        dataset: _DatasetDefinition,
        request: HistoricalLawQuery,
        term: str,
        session: str,
    ) -> tuple[list[tuple[dict[str, Any], str]], bool]:
        url = self._dataset_url(dataset, request, term, session)
        response = self._transport.get(
            url,
            timeout=self.timeout_seconds,
            max_bytes=self.max_response_bytes,
        )
        self._validate_response(response, url, self.max_response_bytes)
        payload = self._decode_payload(response.content)
        values = self._payload_rows(payload)
        complete = len(values) < DATASET_PAGE_SIZE
        bounded_values = values[:DATASET_PAGE_SIZE]
        return [(value, url) for value in bounded_values], complete

    @staticmethod
    def _validate_response(
        response: HttpResponse,
        expected_url: str,
        max_response_bytes: int,
    ) -> None:
        if response.url != expected_url:
            raise ValueError("LEGISLATIVE_YUAN_REDIRECT_NOT_ALLOWED")
        if response.status_code in {301, 302, 303, 307, 308}:
            raise ValueError("LEGISLATIVE_YUAN_REDIRECT_NOT_ALLOWED")
        if response.status_code != 200:
            raise RuntimeError(f"LEGISLATIVE_YUAN_HTTP_STATUS:{response.status_code}")
        if len(response.content) > max_response_bytes:
            raise ValueError("LEGISLATIVE_YUAN_RESPONSE_TOO_LARGE")
        content_type = next(
            (value for key, value in response.headers.items() if key.lower() == "content-type"),
            None,
        )
        if content_type is None:
            raise ValueError("LEGISLATIVE_YUAN_CONTENT_TYPE_MISSING")
        if content_type.split(";", 1)[0].strip().lower() not in {
            "application/json",
            "text/plain",
        }:
            raise ValueError("LEGISLATIVE_YUAN_CONTENT_TYPE_INVALID")

    @staticmethod
    def _decode_payload(content: bytes) -> dict[str, Any]:
        if not isinstance(content, bytes):
            raise ValueError("LEGISLATIVE_YUAN_RESPONSE_BYTES_INVALID")
        try:
            payload = json.loads(
                content.decode("utf-8"),
                parse_constant=_reject_non_finite,
            )
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
            raise ValueError("LEGISLATIVE_YUAN_JSON_INVALID") from exc
        if not isinstance(payload, dict):
            raise ValueError("LEGISLATIVE_YUAN_PAYLOAD_SHAPE_INVALID")
        return payload

    @staticmethod
    def _payload_rows(
        payload: dict[str, Any],
    ) -> list[dict[str, Any]]:
        if "dataList" not in payload or not isinstance(payload["dataList"], list):
            raise ValueError("LEGISLATIVE_YUAN_PAYLOAD_SHAPE_INVALID")
        values = payload["dataList"]
        if any(not isinstance(value, dict) for value in values):
            raise ValueError("LEGISLATIVE_YUAN_ROW_SHAPE_INVALID")
        return values

    def _row_candidates(
        self,
        dataset: _DatasetDefinition,
        row: dict[str, Any],
        *,
        endpoint_url: str,
        ordinal: int,
        request: HistoricalLawQuery,
        document_date: date | None,
    ) -> list[PublicLawCandidate]:
        bill_no = _first_text(row, _BILL_FIELDS)
        term = _first_text(row, _TERM_FIELDS) or request.term
        session = _first_text(row, _SESSION_FIELDS) or request.session
        title = _first_text(row, dataset.title_fields)
        content = _structured_text(row, dataset.text_fields)
        locator_url = self._locator_url(dataset, row, endpoint_url)
        base_id = _candidate_id(dataset.dataset_id, row, term, session)
        record = LegislativeHistoryRecord(
            record_id=base_id,
            role=dataset.role,
            bill_no=bill_no,
            term=term,
            session=session,
            stage=dataset.stage,
            document_date=document_date,
            candidate_id=base_id,
            locator_url=locator_url,
            title=title,
            text=content,
            metadata={
                "dataset_id": dataset.dataset_id,
                "source_endpoint": endpoint_url,
                "locator_only": content is None,
                "structured_dataset_text_present": content is not None,
                "linked_document_fetched": False,
                "pdf_doc_parsing": False,
            },
        )
        return [
            PublicLawCandidate(
                candidate_id=base_id,
                provider_id=self.provider_id,
                material_type=PublicLawMaterialType.LEGISLATIVE_MATERIAL,
                source_role=PublicLawSourceRole.LEGISLATIVE_HISTORY,
                title=record.title,
                excerpt=record.text,
                official_identifier=record.bill_no,
                official_url=record.locator_url,
                candidate_rank=ordinal + 1,
                metadata={
                    "dataset_id": dataset.dataset_id,
                    "legislative_role": record.role.value,
                    "stage": record.stage.value,
                    "bill_no": record.bill_no,
                    "term": record.term,
                    "session": record.session,
                    "legislative_record_json": record.model_dump_json(),
                },
            )
        ]

    def _locator_url(
        self,
        dataset: _DatasetDefinition,
        row: dict[str, Any],
        endpoint_url: str,
    ) -> str:
        locators: list[str] = []
        for field in dataset.locator_fields:
            value = row.get(field)
            if value in (None, ""):
                continue
            if not isinstance(value, str):
                raise ValueError("LEGISLATIVE_YUAN_LOCATOR_SHAPE_INVALID")
            self._validate_payload_url(value)
            locators.append(value)
        return locators[0] if locators else endpoint_url

    @staticmethod
    def _validate_payload_url(value: str) -> None:
        try:
            parsed = urllib.parse.urlparse(value)
            port = parsed.port
        except ValueError as exc:
            raise ValueError("LEGISLATIVE_YUAN_LOCATOR_URL_INVALID") from exc
        if (
            parsed.scheme != "https"
            or parsed.hostname is None
            or parsed.hostname.lower() not in LEGISLATIVE_YUAN_ALLOWED_HOSTS
            or parsed.username is not None
            or parsed.password is not None
            or port not in {None, 443}
            or parsed.fragment
        ):
            raise ValueError("LEGISLATIVE_YUAN_LOCATOR_URL_INVALID")

    def _dataset_url(
        self,
        dataset: _DatasetDefinition,
        request: HistoricalLawQuery,
        term: str,
        session: str,
    ) -> str:
        values = {field: "" for field in dataset.query_fields}
        if "term" in values:
            values["term"] = term
        if "sessionPeriod" in values:
            values["sessionPeriod"] = session
        if dataset.dataset_id == LEGISLATIVE_YUAN_PROPOSAL_DATASET:
            values["billName"] = _law_name_filter(request)
        if "meetingDateE" in values:
            values["meetingDateE"] = _roc_date(request.as_of_date)
        values["fileType"] = "json"
        query = urllib.parse.urlencode(values)
        path = LEGISLATIVE_YUAN_DATASET_PATH_TEMPLATE.format(dataset_id=dataset.dataset_id)
        return f"{self._origin}{path}?{query}"

    @staticmethod
    def _query_scope(request: HistoricalLawQuery) -> tuple[str, str]:
        if request.as_of_date.year <= 1911:
            raise ValueError("LEGISLATIVE_YUAN_AS_OF_DATE_INVALID")
        if request.term is None:
            if request.session is not None:
                raise ValueError("LEGISLATIVE_YUAN_TERM_REQUIRED_WITH_SESSION")
            return "", ""
        term = _digits(request.term)
        if not term or len(term) > 3 or int(term) <= 0:
            raise ValueError("LEGISLATIVE_YUAN_TERM_INVALID")
        if request.session is None:
            return str(int(term)), ""
        session = _digits(request.session)
        if not session or len(session) > 2 or int(session) <= 0:
            raise ValueError("LEGISLATIVE_YUAN_SESSION_INVALID")
        return str(int(term)), session.zfill(2)

    @staticmethod
    def _row_matches(
        dataset: _DatasetDefinition,
        row: dict[str, Any],
        request: HistoricalLawQuery,
        linked_bill_nos: set[str],
    ) -> bool:
        row_bill = _first_text(row, _BILL_FIELDS)
        expected_bill = request.bill_no
        if expected_bill is None and request.law_identifier is not None:
            if re.fullmatch(r"[0-9]{10,20}", request.law_identifier.strip()):
                expected_bill = request.law_identifier.strip()
        row_term = _first_text(row, _TERM_FIELDS)
        if (
            request.term is not None
            and row_term is not None
            and not _same_number(row_term, request.term)
        ):
            return False
        row_session = _first_text(row, _SESSION_FIELDS)
        if (
            request.session is not None
            and row_session is not None
            and not _same_number(row_session, request.session)
        ):
            return False
        needle = request.law_name or request.law_identifier
        title = _first_text(row, dataset.title_fields)
        normalized_needle = _normalize_text(needle) if needle else ""
        title_matches = bool(
            normalized_needle and title and normalized_needle in _normalize_text(title)
        )
        if expected_bill is not None:
            return row_bill == expected_bill if row_bill is not None else title_matches
        if row_bill is not None and row_bill in linked_bill_nos:
            return True
        return title_matches


class LegislativeYuanProviderAdapter(LegislativeHistoryProviderAdapter):
    """Convenience adapter that keeps the common server trust gate."""

    def __init__(
        self,
        *,
        backend: LegislativeHistoryBackend | None = None,
        transport: LegislativeYuanHttpTransport | None = None,
        provider_id: str = LEGISLATIVE_YUAN_PROVIDER_ID,
        metadata_issuer: PublicLawMetadataIssuer | None = None,
        source_promoter: PublicLawSourcePromoter | None = None,
        max_results: int = 20,
        **backend_kwargs: Any,
    ) -> None:
        owned_backend = backend or LegislativeYuanDataBackend(
            transport=transport,
            max_results=max_results,
            **backend_kwargs,
        )
        super().__init__(
            provider_id=provider_id,
            backend=owned_backend,
            metadata_issuer=metadata_issuer,
            source_promoter=source_promoter,
            max_results=max_results,
        )


# Short names make the optional connector discoverable without changing the
# existing LegislativeHistoryBackend/Adapter contract.
LegislativeYuanBackend = LegislativeYuanDataBackend
LegislativeYuanConnector = LegislativeYuanProviderAdapter


def _first_text(row: dict[str, Any], fields: tuple[str, ...]) -> str | None:
    for field in fields:
        value = row.get(field)
        if value in (None, ""):
            continue
        if not isinstance(value, str):
            raise ValueError("LEGISLATIVE_YUAN_FIELD_SHAPE_INVALID")
        text = value.strip()
        if text:
            return text
    return None


def _structured_text(row: dict[str, Any], fields: tuple[str, ...]) -> str | None:
    parts: list[str] = []
    for field in fields:
        value = row.get(field)
        if value in (None, ""):
            continue
        if not isinstance(value, str):
            raise ValueError("LEGISLATIVE_YUAN_FIELD_SHAPE_INVALID")
        text = value.strip()
        if text:
            parts.append(f"{field}: {text}")
    if not parts:
        return None
    result = "\n".join(parts)
    if len(result) > 4000:
        raise ValueError("LEGISLATIVE_YUAN_STRUCTURED_TEXT_TOO_LARGE")
    return result


def _candidate_id(
    dataset_id: str,
    row: dict[str, Any],
    term: str | None,
    session: str | None,
) -> str:
    canonical = json.dumps(
        {
            "dataset_id": dataset_id,
            "term": term,
            "session": session,
            "row": row,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    digest = hashlib.sha256(canonical).hexdigest()[:40]
    return f"ly:{dataset_id}:{digest}"


def _parse_document_date(
    row: dict[str, Any],
    fields: tuple[str, ...],
) -> date | None:
    value = _first_text(row, fields)
    if value is None:
        return None
    parts = [part.strip() for part in re.split(r"[,，]", value) if part.strip()]
    if not parts:
        raise ValueError("LEGISLATIVE_YUAN_DOCUMENT_DATE_INVALID")
    return max(_parse_single_document_date(part) for part in parts)


def _parse_single_document_date(value: str) -> date:
    normalized = value.replace("/", "-").strip()
    if re.fullmatch(r"[0-9]{7}", normalized):
        try:
            return date(
                int(normalized[:3]) + 1911,
                int(normalized[3:5]),
                int(normalized[5:]),
            )
        except ValueError as exc:
            raise ValueError("LEGISLATIVE_YUAN_DOCUMENT_DATE_INVALID") from exc
    for fmt in ("%Y-%m-%d", "%Y%m%d"):
        try:
            return datetime.strptime(normalized, fmt).date()
        except ValueError:
            continue
    roc_match = re.fullmatch(
        r"(?:民國)?([0-9]{3})(?:年|-)([0-9]{1,2})(?:月|-)([0-9]{1,2})日?",
        normalized,
    )
    if roc_match is not None:
        try:
            return date(
                int(roc_match.group(1)) + 1911,
                int(roc_match.group(2)),
                int(roc_match.group(3)),
            )
        except ValueError as exc:
            raise ValueError("LEGISLATIVE_YUAN_DOCUMENT_DATE_INVALID") from exc
    raise ValueError("LEGISLATIVE_YUAN_DOCUMENT_DATE_INVALID")


def _normalize_text(value: str) -> str:
    return re.sub(r"[\W_]+", "", value.casefold(), flags=re.UNICODE)


def _law_name_filter(request: HistoricalLawQuery) -> str:
    if request.law_name is not None:
        return request.law_name.strip()
    identifier = (request.law_identifier or "").strip()
    return "" if re.fullmatch(r"[0-9]{10,20}", identifier) else identifier


def _roc_date(value: date) -> str:
    return f"{value.year - 1911:03d}/{value.month:02d}/{value.day:02d}"


def _same_number(left: str, right: str) -> bool:
    left_digits = _digits(left)
    right_digits = _digits(right)
    return bool(left_digits and right_digits and int(left_digits) == int(right_digits))


def _digits(value: str) -> str:
    text = str(value).strip()
    return text if text.isdigit() else ""


class _RejectRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *_args: Any, **_kwargs: Any) -> None:
        raise RuntimeError("LEGISLATIVE_YUAN_REDIRECT_NOT_ALLOWED")


def _official_ssl_context() -> ssl.SSLContext:
    """Return a verified TLS context scoped to the fixed official data host."""
    context = ssl.create_default_context()
    legacy_server_connect = getattr(ssl, "OP_LEGACY_SERVER_CONNECT", None)
    if legacy_server_connect is not None:
        context.options |= legacy_server_connect
    no_renegotiation = getattr(ssl, "OP_NO_RENEGOTIATION", None)
    if no_renegotiation is not None:
        context.options |= no_renegotiation
    return context


def _reject_non_finite(value: str) -> None:
    raise ValueError(f"LEGISLATIVE_YUAN_NON_FINITE:{value}")


__all__ = [
    "DATASET_PAGE_SIZE",
    "LEGISLATIVE_YUAN_ALLOWED_HOSTS",
    "LEGISLATIVE_YUAN_ARTICLE_COMPARISON_DATASET",
    "LEGISLATIVE_YUAN_CAUCUS_DATASET",
    "LEGISLATIVE_YUAN_COMMITTEE_DATASET",
    "LEGISLATIVE_YUAN_DATA_ORIGIN",
    "LEGISLATIVE_YUAN_DATA_HOST",
    "LEGISLATIVE_YUAN_DATASET_PATH_TEMPLATE",
    "LEGISLATIVE_YUAN_PROPOSAL_DATASET",
    "LEGISLATIVE_YUAN_PROVIDER_ID",
    "LEGISLATIVE_YUAN_THIRD_READING_DATASET",
    "LEGISLATIVE_YUAN_UNSUPPORTED_DATASET_IDS",
    "LegislativeYuanBackend",
    "LegislativeYuanConnector",
    "LegislativeYuanDataBackend",
    "LegislativeYuanHttpClient",
    "LegislativeYuanHttpTransport",
    "LegislativeYuanProviderAdapter",
]
