"""Adapter port for a deployer-owned Legislative Yuan history connector.

This module intentionally does not know the Legislative Yuan endpoint or
authentication scheme.  It translates a typed historical-law query into the
existing bounded public-law SDK, then separates normative law-version source
IDs from legislative-history source IDs.  The server metadata issuer and
source promoter remain the only trust gates.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from alr_tw.contracts.historical_law import (
    HistoricalLawQuery,
    HistoricalLawResolution,
)
from alr_tw.contracts.public_law import (
    PublicLawMaterialType,
    PublicLawProviderCapabilities,
    PublicLawProviderResult,
    PublicLawResultStatus,
    PublicLawSearchRequest,
)
from alr_tw.providers.sdk import (
    GenericPublicLawProviderAdapter,
    PublicLawBackendResult,
    PublicLawMetadataIssuer,
    PublicLawSourcePromoter,
)


@runtime_checkable
class LegislativeHistoryBackend(Protocol):
    """Minimal connector port implemented by the deployment owner."""

    def search(self, request: HistoricalLawQuery) -> PublicLawBackendResult: ...


class _RequestBridge:
    """Adapt one immutable historical query to the generic SDK backend port."""

    def __init__(
        self,
        backend: LegislativeHistoryBackend,
        request: HistoricalLawQuery,
    ) -> None:
        self._backend = backend
        self._request = request

    def search(self, _request: PublicLawSearchRequest) -> PublicLawBackendResult:
        return self._backend.search(self._request)


class LegislativeHistoryProviderAdapter:
    """Bounded provider-neutral adapter for Legislative Yuan history data."""

    def __init__(
        self,
        *,
        provider_id: str,
        backend: LegislativeHistoryBackend,
        metadata_issuer: PublicLawMetadataIssuer | None = None,
        source_promoter: PublicLawSourcePromoter | None = None,
        max_results: int = 20,
    ) -> None:
        self._provider_id = provider_id
        self._backend = backend
        self._metadata_issuer = metadata_issuer
        self._source_promoter = source_promoter
        self._max_results = max(1, min(max_results, 50))

    @property
    def provider_id(self) -> str:
        return self._provider_id

    def capabilities(self) -> PublicLawProviderCapabilities:
        """Return the common SDK capability envelope."""

        adapter = GenericPublicLawProviderAdapter(
            provider_id=self._provider_id,
            backend=_RequestBridge(self._backend, self._capability_query()),
            material_types=(
                PublicLawMaterialType.HISTORICAL_STATUTE,
                PublicLawMaterialType.LEGISLATIVE_MATERIAL,
            ),
            metadata_issuer=self._metadata_issuer,
            source_promoter=self._source_promoter,
            max_results=self._max_results,
            exact_lookup=True,
            historical_versions=True,
            server_verification=self._metadata_issuer is not None,
        )
        return adapter.capabilities()

    def search(self, request: HistoricalLawQuery) -> HistoricalLawResolution:
        query = request.model_copy(
            update={"max_results": min(request.max_results, self._max_results)}
        )
        public_request = PublicLawSearchRequest(
            query_id=query.query_id,
            query=" ".join(
                value for value in (query.law_identifier, query.law_name) if value
            ),
            material_types=[
                PublicLawMaterialType.HISTORICAL_STATUTE,
                *(
                    [PublicLawMaterialType.LEGISLATIVE_MATERIAL]
                    if query.include_legislative_history
                    else []
                ),
            ],
            bounded_scope=query.bounded_scope,
            max_results=query.max_results,
            as_of_date=query.as_of_date,
        )
        adapter = GenericPublicLawProviderAdapter(
            provider_id=self._provider_id,
            backend=_RequestBridge(self._backend, query),
            material_types=tuple(public_request.material_types),
            metadata_issuer=self._metadata_issuer,
            source_promoter=self._source_promoter,
            max_results=self._max_results,
            exact_lookup=True,
            historical_versions=True,
            server_verification=self._metadata_issuer is not None,
        )
        result = adapter.search(public_request)
        return self._resolution(query, result)

    def _resolution(
        self,
        query: HistoricalLawQuery,
        result: PublicLawProviderResult,
    ) -> HistoricalLawResolution:
        normative = [
            source.source_id
            for source in result.sources
            if source.material_type is PublicLawMaterialType.HISTORICAL_STATUTE
        ]
        legislative = [
            source.source_id
            for source in result.sources
            if source.material_type is PublicLawMaterialType.LEGISLATIVE_MATERIAL
        ]
        try:
            return HistoricalLawResolution(
                query_id=query.query_id,
                provider_id=self._provider_id,
                law_identifier=query.law_identifier or query.law_name or "unknown",
                as_of_date=query.as_of_date,
                bounded_scope=query.bounded_scope,
                provider_result=result,
                normative_source_ids=normative,
                legislative_material_source_ids=legislative,
                warnings=(
                    []
                    if normative
                    else ["HISTORICAL_LAW_NORMATIVE_SOURCE_MISSING"]
                ),
            )
        except ValueError:
            blocked = result.model_copy(
                update={
                    "provider_id": self._provider_id,
                    "query_id": query.query_id,
                    "bounded_scope": query.bounded_scope,
                    "status": PublicLawResultStatus.BLOCKED,
                    "candidates": [],
                    "sources": [],
                    "coverage_complete": False,
                    "absence_claim_allowed": False,
                    "reason_codes": ["HISTORICAL_LAW_SOURCE_ROLE_INVALID"],
                }
            )
            return HistoricalLawResolution(
                query_id=query.query_id,
                provider_id=self._provider_id,
                law_identifier=query.law_identifier or query.law_name or "unknown",
                as_of_date=query.as_of_date,
                bounded_scope=query.bounded_scope,
                provider_result=blocked,
                warnings=["HISTORICAL_LAW_SOURCE_ROLE_INVALID"],
            )

    @staticmethod
    def _capability_query() -> HistoricalLawQuery:
        from datetime import date

        return HistoricalLawQuery(
            query_id="capability-probe",
            law_name="capability-probe",
            as_of_date=date(1970, 1, 1),
            bounded_scope="capability-probe",
        )


__all__ = ["LegislativeHistoryBackend", "LegislativeHistoryProviderAdapter"]
