"""Optional bounded MOJ historical-text and interpretation verification.

These providers verify source text/identity. They do not decide case applicability
or infer current effect from an old document's continued presence on the website.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from datetime import UTC, date, datetime, timedelta
from uuid import uuid4

from alr_tw.contracts.historical_law import HistoricalLawQuery, HistoricalLawResolution
from alr_tw.contracts.public_law import (
    PublicLawMaterialType,
    PublicLawProviderResult,
    PublicLawResultStatus,
    PublicLawServerMetadata,
    PublicLawSourceRecord,
    PublicLawSourceRole,
)
from alr_tw.contracts.sources import SourceTier, TrustStatus
from alr_tw.providers.official.http import HttpTransport, HttpxAllowlistedTransport


def _compact(text: str) -> str:
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", text))


def _roc_date(text: str) -> date | None:
    match = re.search(r"民國\s*(\d+)\s*年\s*(\d+)\s*月\s*(\d+)\s*日", text)
    if not match:
        return None
    try:
        return date(int(match[1]) + 1911, int(match[2]), int(match[3]))
    except ValueError:
        return None


def _metadata(provider_id: str, text: str, now: datetime) -> PublicLawServerMetadata:
    digest = "sha256:" + hashlib.sha256(text.encode()).hexdigest()
    return PublicLawServerMetadata(
        provider_id=provider_id,
        snapshot_id="s-" + digest[7:31],
        generation="v1",
        receipt_id="r-" + uuid4().hex,
        issued_at=now,
        expires_at=now + timedelta(hours=1),
        content_digest=digest,
    )


def _source(
    provider_id: str,
    identifier: str,
    url: str,
    text: str,
    title: str,
    material: PublicLawMaterialType,
    role: PublicLawSourceRole,
    now: datetime,
    issued: date,
    details: dict,
) -> PublicLawSourceRecord:
    metadata = _metadata(provider_id, text, now)
    digest = metadata.content_digest
    assert digest is not None
    return PublicLawSourceRecord(
        source_id="src-" + hashlib.sha256((identifier + text).encode()).hexdigest()[:32],
        source_key=identifier,
        source_version_id=issued.isoformat() + ":" + digest[7:23],
        material_type=material,
        source_role=role,
        provider_id=provider_id,
        source_tier=SourceTier.OFFICIAL,
        trust_status=TrustStatus.OFFICIAL_VERIFIED,
        official_identifier=identifier,
        official_url=url,
        citation=title,
        title=title,
        issued_at=datetime.combine(issued, datetime.min.time(), tzinfo=UTC),
        fetched_at=now,
        verified_at=now,
        expires_at=now + timedelta(hours=1),
        content_hash=digest,
        normalized_content_hash=digest,
        normalized_text=text,
        server_metadata=metadata,
        metadata=details,
        warnings=["SOURCE_TEXT_VERIFIED_NOT_CASE_APPLICABILITY"],
    )


class OfficialHistoricalLawProvider:
    provider_id = "official-historical-moj"
    # Small, declared pilot. No claim to choose a currently applicable statute.
    revisions = {"B0000001": (date(2019, 6, 19), date(2021, 1, 13), date(2021, 1, 20))}
    supported_until = date(2021, 12, 31)

    def __init__(self, transport: HttpTransport | None = None):
        self.transport = transport or HttpxAllowlistedTransport({"law.moj.gov.tw"})

    def supported_scope(self) -> dict:
        return {
            "laws": {
                key: [v.isoformat() for v in values] for key, values in self.revisions.items()
            },
            "until": self.supported_until.isoformat(),
            "coverage_complete": False,
            "selection_basis": "promulgated_version_not_effective_or_case_applicable",
        }

    async def lookup(self, query: HistoricalLawQuery, article_no: str) -> HistoricalLawResolution:
        law = query.law_identifier or ""
        if not re.fullmatch(r"\d{1,4}(?:-\d{1,3})?", article_no):
            raise ValueError("HISTORICAL_ARTICLE_INVALID")
        versions = [v for v in self.revisions.get(law, ()) if v <= query.as_of_date]
        source = None
        reasons: list[str] = []
        status = PublicLawResultStatus.BLOCKED
        if not versions or query.as_of_date > self.supported_until:
            reasons.append("HISTORICAL_SCOPE_UNSUPPORTED")
        else:
            version = max(versions)
            url = (
                "https://law.moj.gov.tw/LawClass/LawOldVer.aspx?pcode="
                + law
                + "&lnndate="
                + version.strftime("%Y%m%d")
                + "&lser=001"
            )
            response = await self.transport.get(url, timeout=20, max_bytes=1500000)
            if response.status_code != 200 or response.url != url:
                raise ValueError("HISTORICAL_TRANSPORT_FAILED")
            from bs4 import BeautifulSoup

            soup = BeautifulSoup(response.content, "html.parser")
            fields: dict[str, str] = {}
            for row in soup.select("tr"):
                heading, value = row.find("th", recursive=False), row.find("td", recursive=False)
                if heading and value:
                    label = _compact(heading.get_text()).rstrip(":：")
                    if label in {"法規名稱", "修正日期"}:
                        if label in fields:
                            raise ValueError("HISTORICAL_SOURCE_AMBIGUOUS")
                        fields[label] = _compact(value.get_text())
            if fields.get("法規名稱") != "民法" or (
                query.law_name is not None and _compact(query.law_name) != "民法"
            ):
                raise ValueError("HISTORICAL_IDENTITY_MISMATCH")
            date_text = fields.get("修正日期", "")
            if not re.fullmatch(r"民國\d+年\d+月\d+日", date_text) or _roc_date(date_text) != version:
                raise ValueError("HISTORICAL_VERSION_MISMATCH")
            matches = []
            for row in soup.select(".row"):
                number, body = row.select_one(".col-no"), row.select_one(".col-data")
                if number and body and _compact(number.get_text()) == "第" + article_no + "條":
                    matches.append(body.get_text("\n", strip=True))
            if len(matches) > 1:
                raise ValueError("HISTORICAL_SOURCE_AMBIGUOUS")
            if not matches:
                status = PublicLawResultStatus.BLOCKED
                reasons.append("HISTORICAL_ARTICLE_NOT_FOUND_IN_VERSION")
            else:
                text = matches[0]
                if not text or len(text) > 20000:
                    raise ValueError("HISTORICAL_TEXT_INVALID")
                now = datetime.now(UTC)
                source = _source(
                    self.provider_id,
                    law + ":" + article_no,
                    url,
                    text,
                    "民法第" + article_no + "條（歷史文本）",
                    PublicLawMaterialType.HISTORICAL_STATUTE,
                    PublicLawSourceRole.NORMATIVE_RULE,
                    now,
                    version,
                    {
                        "version_date": version.isoformat(),
                        "effective_status": "unresolved",
                        "applicability_status": "requires_server_adjudication",
                        "as_of_date": query.as_of_date.isoformat(),
                    },
                )
                status = PublicLawResultStatus.FOUND
                reasons.append("HISTORICAL_EFFECTIVITY_NOT_ESTABLISHED")
        result = PublicLawProviderResult(
            provider_id=self.provider_id,
            query_id=query.query_id,
            status=status,
            bounded_scope=query.bounded_scope,
            sources=[source] if source else [],
            server_metadata=source.server_metadata if source else None,
            reason_codes=reasons,
        )
        return HistoricalLawResolution(
            query_id=query.query_id,
            provider_id=self.provider_id,
            law_identifier=law or query.law_name or "unsupported",
            as_of_date=query.as_of_date,
            bounded_scope=query.bounded_scope,
            provider_result=result,
            normative_source_ids=[source.source_id] if source else [],
            warnings=reasons,
        )


class OfficialInterpretationProvider:
    provider_id = "official-interpretation-moj"

    def __init__(self, transport: HttpTransport | None = None):
        self.transport = transport or HttpxAllowlistedTransport({"mojlaw.moj.gov.tw"})

    async def lookup(self, document_id: str, expected_number: str) -> PublicLawProviderResult:
        if not re.fullmatch(r"FE\d{6}", document_id) or not 1 <= len(expected_number) <= 200:
            raise ValueError("INTERPRETATION_IDENTITY_INVALID")
        url = "https://mojlaw.moj.gov.tw/LawContentExShow.aspx?id=" + document_id + "&type=E"
        response = await self.transport.get(url, timeout=20, max_bytes=1500000)
        if response.status_code != 200 or response.url != url:
            raise ValueError("INTERPRETATION_TRANSPORT_FAILED")
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(response.content, "html.parser")
        fields: dict[str, str] = {}
        for row in soup.select(".col-row"):
            key, value = row.select_one(".col-th"), row.select_one(".col-td")
            if key and value:
                name = _compact(key.get_text()).rstrip(":：")
                if name in fields:
                    raise ValueError("INTERPRETATION_IDENTITY_AMBIGUOUS")
                fields[name] = value.get_text("\n", strip=True)
        number = fields.get("發文字號", "")
        issued = _roc_date(fields.get("發文日期", ""))
        if (
            _compact(number) != _compact(expected_number)
            or issued is None
            or not fields.get("發文單位")
        ):
            raise ValueError("INTERPRETATION_IDENTITY_MISMATCH")
        full = soup.select("#cp_content_EFULLtr pre")
        if len(full) != 1:
            raise ValueError("INTERPRETATION_FULLTEXT_REQUIRED")
        text = full[0].get_text().strip()
        if text.startswith("全文內容："):
            text = text[len("全文內容：") :].strip()
        if not text or len(text) > 20000:
            raise ValueError("INTERPRETATION_TEXT_INVALID")
        effect = "unknown"
        # Only recognized, affirmative metadata establishes a status. Body text,
        # placeholders, questions and negation cannot supply effectivity.
        for label, state in (("廢止日期", "repealed"), ("停止適用日期", "stopped")):
            date_value = _compact(fields.get(label, ""))
            parsed = _roc_date(date_value)
            if re.fullmatch(r"民國\d+年\d+月\d+日", date_value) and parsed and parsed <= date.today():
                effect = state
                break
        if effect == "unknown":
            effect = {
                "部分停止適用": "partially_stopped",
                "由新函取代": "superseded",
            }.get(_compact(fields.get("效力註記", "")), "unknown")
        source = _source(
            self.provider_id,
            document_id + ":" + number,
            url,
            text,
            number,
            PublicLawMaterialType.ADMINISTRATIVE_INTERPRETATION,
            PublicLawSourceRole.INTERPRETIVE_GUIDANCE,
            datetime.now(UTC),
            issued,
            {
                "issuing_authority": fields["發文單位"],
                "effectivity_status": effect,
                "effectivity_basis": fields.get(
                    "效力註記", fields.get("廢止日期", fields.get("停止適用日期", "unknown"))
                ),
                "attachments_resolved": False,
            },
        )
        return PublicLawProviderResult(
            provider_id=self.provider_id,
            query_id="q-" + uuid4().hex,
            status=PublicLawResultStatus.FOUND,
            bounded_scope="one-exact-official-interpretation",
            sources=[source],
            server_metadata=source.server_metadata,
            reason_codes=["INTERPRETATION_EFFECTIVITY_UNKNOWN"] if effect == "unknown" else [],
            metadata={"legal_entailment_authorized": False},
        )
