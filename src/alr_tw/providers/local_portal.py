"""Read-only adapter for the optional ``legal_data_pipeline`` portal.

Search projections and snippets remain candidate-only.  Exact lookups check
catalog-bound metadata and trusted-text hashes before creating server-owned
verified-cache records; otherwise they fall back to the official provider.
"""

from __future__ import annotations

import hashlib
import importlib
import json
import os
import re
import sys
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Protocol

from alr_tw.contracts.providers import (
    CandidateIdentity,
    ProviderCapabilities,
    ProviderCandidate,
    ProviderErrorCode,
    ProviderHealth,
    ProviderHealthStatus,
    ProviderResult,
    ProviderResultStatus,
)
from alr_tw.contracts.sources import (
    EvidenceSectionType,
    EvidenceSpan,
    MaterialType,
    SourceRecord,
    SourceTier,
    TrustStatus,
)
from alr_tw.providers.official.judgments import OfficialJudgmentProvider


LOCAL_PORTAL_PROVIDER_ID = "local_read_only_judicial_portal"
LOCAL_PORTAL_ROOT_ENV = "ALR_TW_LOCAL_PORTAL_ROOT"
_MAX_RESULTS = 20
_MAX_TEXT = 4096
_MAX_TRUSTED_TEXT = 20_000
_LOCAL_SNAPSHOT_TTL = timedelta(hours=24)
_SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_SAFE_COVERAGE_FIELDS = {
    "coverage_complete",
    "absence_claim_allowed",
    "partial",
    "snapshot_consistency",
    "binding_status",
    "catalog_snapshot_id",
    "catalog_release_id",
    "selected_index_count",
    "successful_query_index_count",
    "available_index_count",
    "blocking_reasons",
}


class PortalCapabilityClient(Protocol):
    def call_capability(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]: ...


class JudgmentProviderPort(Protocol):
    """Common judgment operations used by the provider-backed research service."""

    provider_id: str

    def capabilities(self) -> ProviderCapabilities: ...

    async def health_check(self) -> ProviderHealth: ...

    async def search(self, query: str = "", *, limit: int = 10) -> ProviderResult: ...

    async def exact_lookup(
        self,
        identifier: str,
        *,
        now: datetime | None = None,
    ) -> tuple[ProviderResult, SourceRecord | None, list[EvidenceSpan]]: ...


def _bounded_text(value: Any, *, default: str = "") -> str:
    if not isinstance(value, str):
        return default
    value = value.strip()
    if not value or "\x00" in value:
        return default
    return value[:_MAX_TEXT]


def _safe_identifier(value: Any) -> str:
    value = _bounded_text(value)
    if not value or "/" in value or "\\" in value or "sqlite" in value.lower():
        return ""
    return value


def _safe_coverage(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    output: dict[str, Any] = {}
    for key in _SAFE_COVERAGE_FIELDS:
        item = value.get(key)
        if key == "blocking_reasons":
            if isinstance(item, list):
                codes = [
                    code[:128]
                    for code in item
                    if isinstance(code, str)
                    and code
                    and "/" not in code
                    and "\\" not in code
                ]
                output[key] = sorted(set(codes))[:32]
            continue
        if type(item) in (str, bool, int, float) and not (
            isinstance(item, str) and ("/" in item or "\\" in item)
        ):
            output[key] = item
    return output


def _canonical_sha256(value: Any) -> str:
    text = value.strip() if isinstance(value, str) else ""
    if re.fullmatch(r"[0-9a-f]{64}", text):
        text = f"sha256:{text}"
    return text if _SHA256_RE.fullmatch(text) else ""


def _canonical_json_digest(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        dict(value), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def _request_receipt_is_catalog_bound(
    receipt: Any,
    coverage: Mapping[str, Any],
) -> bool:
    if not isinstance(receipt, Mapping):
        return False
    expected_keys = {
        "schema",
        "binding_status",
        "catalog_snapshot_id",
        "catalog_release_id",
        "catalog_artifact_ids",
        "registry_snapshot_id",
        "context_digest",
    }
    if set(receipt) != expected_keys or receipt.get("binding_status") != "catalog_bound":
        return False
    snapshot_id = receipt.get("catalog_snapshot_id")
    release_id = receipt.get("catalog_release_id")
    registry_snapshot_id = receipt.get("registry_snapshot_id")
    artifact_ids = receipt.get("catalog_artifact_ids")
    if (
        not isinstance(receipt.get("schema"), str)
        or not receipt["schema"].endswith("judgment-request-context/v1")
        or not _canonical_sha256(snapshot_id)
        or not _bounded_text(release_id)
        or not _canonical_sha256(registry_snapshot_id)
        or not isinstance(artifact_ids, list)
        or not artifact_ids
        or any(not _safe_identifier(item) for item in artifact_ids)
        or artifact_ids != sorted(set(artifact_ids))
    ):
        return False
    unsigned = dict(receipt)
    unsigned.pop("context_digest", None)
    if _canonical_sha256(receipt.get("context_digest")) != _canonical_json_digest(unsigned):
        return False
    return (
        coverage.get("binding_status") == "catalog_bound"
        and coverage.get("catalog_snapshot_id") == snapshot_id
        and coverage.get("catalog_release_id") == release_id
    )


def _provenance(item: Mapping[str, Any]) -> dict[str, Any]:
    nested = item.get("metadata")
    metadata = nested if isinstance(nested, Mapping) else {}
    values: dict[str, Any] = {}
    for key in (
        "verification_status",
        "local_verified",
        "citation_allowed",
        "registry_status",
        "catalog_artifact_id",
        "source_hash",
        "judgment_context_digest",
        "chunk_id",
    ):
        value = item.get(key, metadata.get(key))
        if type(value) in (str, bool, int, float):
            values[key] = value
    return values


def _trusted_text_hash_matches(text: str, item: Mapping[str, Any], payload: Mapping[str, Any]) -> bool:
    expected = (
        payload.get("trusted_text_hash")
        or item.get("trusted_text_hash")
        or item.get("text_hash")
    )
    return bool(_canonical_sha256(expected)) and hmac_compare_digest(
        _canonical_sha256(expected), EvidenceSpan.hash_text(text)
    )


def hmac_compare_digest(left: str, right: str) -> bool:
    # Kept local so hash comparisons do not become ordinary short-circuit
    # string comparisons at this trust boundary.
    import hmac

    return hmac.compare_digest(left, right)


def _candidate_from_item(item: Any, rank: int) -> ProviderCandidate | None:
    if not isinstance(item, Mapping):
        return None
    jid = _safe_identifier(item.get("jid"))
    source_id = _safe_identifier(item.get("source_id"))
    if not jid:
        jid = source_id
    if not jid:
        return None
    canonical = OfficialJudgmentProvider.normalize_jid(jid)
    provider_document_id = source_id or jid
    candidate_key = f"{jid}\x00{provider_document_id}"
    candidate_id = "local-portal:" + hashlib.sha256(candidate_key.encode("utf-8")).hexdigest()[:24]
    snippet = _bounded_text(item.get("snippet") or item.get("excerpt"))
    metadata: dict[str, Any] = {
        "candidate_only": True,
        "snippet_only": True,
        "local_portal": True,
        "source_type": _bounded_text(item.get("source_type"), default="judgment"),
        "date": _bounded_text(item.get("date")),
        "section_role": _bounded_text(item.get("section_role")),
    }
    metadata.update(_provenance(item))
    item_metadata = item.get("metadata")
    if isinstance(item_metadata, Mapping):
        metadata["local_metadata_keys"] = sorted(
            key[:64]
            for key in item_metadata
            if isinstance(key, str) and key and "/" not in key and "\\" not in key
        )[:32]
    return ProviderCandidate(
        candidate_id=candidate_id,
        provider_id=LOCAL_PORTAL_PROVIDER_ID,
        title=_bounded_text(item.get("title"), default="裁判書"),
        official_identifier=jid,
        excerpt=snippet or None,
        identity=CandidateIdentity(
            canonical_jid=canonical,
            provider_document_id=provider_document_id,
            official_url=None,
        ),
        candidate_rank=rank,
        metadata=metadata,
    )


def _data_paths_for_root(data_paths_type: Any, root: Path) -> Any:
    """Construct the external DataPaths without consulting process env vars."""

    # The deployment setting accepts either the checkout root or the
    # ``data/legal_public`` root.  Resolve only these two deterministic
    # layouts; never walk the filesystem looking for a database.
    public_root = root / "data" / "legal_public"
    if not public_root.is_dir():
        public_root = root
    return data_paths_type(
        public_root=public_root,
        judgments_root=public_root / "judgments",
        judgments_index_dir=public_root / "judgments" / "index",
        judgments_raw_dir=public_root / "judgments" / "raw",
        laws_chroma_dir=public_root / "laws" / "chroma",
        constitutional_dir=public_root / "constitutional",
    )


def _source_roots(root: Path) -> tuple[Path, ...]:
    """Return only deterministic source layouts; never scan the filesystem."""

    candidates = (root / "src", root.parent / "src", root.parent.parent / "src", root.parent)
    return tuple(dict.fromkeys(path for path in candidates if path.is_dir()))


def _load_portal(root: Path) -> tuple[PortalCapabilityClient | None, str | None]:
    """Load the optional package, preferably from the normal interpreter path."""

    try:
        config = importlib.import_module("legal_data_pipeline.config")
        portal_module = importlib.import_module("legal_data_pipeline.portal_provider")
    except Exception:
        config = None
        portal_module = None

    if config is None or portal_module is None:
        for source_root in _source_roots(root):
            package_dir = source_root / "legal_data_pipeline"
            if not package_dir.is_dir():
                continue
            sys.path.insert(0, str(source_root))
            try:
                config = importlib.import_module("legal_data_pipeline.config")
                portal_module = importlib.import_module("legal_data_pipeline.portal_provider")
                break
            except Exception:
                config = None
                portal_module = None
            finally:
                try:
                    sys.path.remove(str(source_root))
                except ValueError:
                    pass

    if config is None or portal_module is None:
        return None, "PORTAL_PACKAGE_UNAVAILABLE"
    try:
        data_paths_type = getattr(config, "DataPaths")
        builder = getattr(portal_module, "build_read_only_portal_provider")
        paths = _data_paths_for_root(data_paths_type, root)
        portal = builder(paths)
    except Exception:
        return None, "PORTAL_PROVIDER_BUILD_FAILED"
    if not hasattr(portal, "call_capability"):
        return None, "PORTAL_PROVIDER_INTERFACE_INVALID"
    return portal, None


class LocalPortalJudgmentProvider:
    """Composite judgment provider with local candidate recall and official verification."""

    provider_id = LOCAL_PORTAL_PROVIDER_ID

    def __init__(
        self,
        root: Path,
        *,
        official_provider: JudgmentProviderPort | None = None,
        portal: PortalCapabilityClient | None = None,
        load_error: str | None = None,
    ) -> None:
        if not root.is_absolute():
            raise ValueError("local portal root must be absolute")
        self.root = root
        self.official_provider = official_provider or OfficialJudgmentProvider()
        if portal is None and load_error is None:
            portal, load_error = _load_portal(root)
        self._portal = portal
        self._load_error = load_error

    def capabilities(self) -> ProviderCapabilities:
        official = self.official_provider.capabilities()
        return official.model_copy(update={"keyword_search": True, "exact_lookup": True})

    async def health_check(self) -> ProviderHealth:
        if self._portal is None:
            return ProviderHealth(
                provider_id=self.provider_id,
                status=ProviderHealthStatus.UNAVAILABLE,
                error_code=ProviderErrorCode.EXTERNAL_PROVIDER_UNAVAILABLE.value,
                message=self._load_error or "PORTAL_PROVIDER_UNAVAILABLE",
            )
        return ProviderHealth(provider_id=self.provider_id, status=ProviderHealthStatus.HEALTHY)

    def _error(self, code: ProviderErrorCode, message: str) -> ProviderResult:
        return ProviderResult(
            status=ProviderResultStatus.ERROR,
            provider_id=self.provider_id,
            error_code=code,
            message=message,
            coverage_complete=False,
            metadata={"local_portal": True, "candidate_only": True},
        )

    def _call(self, capability: str, arguments: dict[str, Any]) -> ProviderResult:
        if self._portal is None:
            return self._error(
                ProviderErrorCode.EXTERNAL_PROVIDER_UNAVAILABLE,
                self._load_error or "PORTAL_PROVIDER_UNAVAILABLE",
            )
        try:
            payload = self._portal.call_capability(capability, arguments)
        except Exception:
            return self._error(
                ProviderErrorCode.EXTERNAL_PROVIDER_UNAVAILABLE,
                "PORTAL_PROVIDER_CALL_FAILED",
            )
        if not isinstance(payload, Mapping):
            return self._error(
                ProviderErrorCode.EXTERNAL_PROVIDER_SCHEMA_CHANGED,
                "PORTAL_PROVIDER_RESPONSE_INVALID",
            )
        if payload.get("writes_performed") is not False:
            return self._error(
                ProviderErrorCode.EXTERNAL_PROVIDER_SCHEMA_CHANGED,
                "PORTAL_PROVIDER_WRITE_FLAG_INVALID",
            )
        if payload.get("status") == "source_unavailable" or payload.get("success") is False:
            return self._error(
                ProviderErrorCode.EXTERNAL_PROVIDER_UNAVAILABLE,
                "PORTAL_PROVIDER_SOURCE_UNAVAILABLE",
            ).model_copy(update={"metadata": {"coverage": _safe_coverage(payload.get("coverage"))}})
        if payload.get("status") != "success" or payload.get("success") is not True:
            return self._error(
                ProviderErrorCode.EXTERNAL_PROVIDER_SCHEMA_CHANGED,
                "PORTAL_PROVIDER_RESPONSE_STATUS_INVALID",
            )
        raw_results = payload.get("results")
        if not isinstance(raw_results, list):
            return self._error(
                ProviderErrorCode.EXTERNAL_PROVIDER_SCHEMA_CHANGED,
                "PORTAL_PROVIDER_RESULTS_INVALID",
            )
        candidates = [
            candidate
            for rank, item in enumerate(raw_results[:_MAX_RESULTS], start=1)
            if (candidate := _candidate_from_item(item, rank)) is not None
        ]
        if payload.get("found") is True and not candidates:
            return self._error(
                ProviderErrorCode.EXTERNAL_PROVIDER_SCHEMA_CHANGED,
                "PORTAL_PROVIDER_RESULT_PROJECTION_INVALID",
            )
        coverage = _safe_coverage(payload.get("coverage"))
        result_metadata: dict[str, Any] = {
            "local_portal": True,
            "candidate_only": True,
            "retrieval": payload.get("mode", "local_read_only"),
            "coverage": coverage,
        }
        receipt = payload.get("judgment_request_context")
        trusted_text = payload.get("trusted_text")
        if (
            candidates
            and isinstance(receipt, Mapping)
            and _request_receipt_is_catalog_bound(receipt, coverage)
            and isinstance(trusted_text, str)
            and trusted_text.strip()
            and len(trusted_text) <= _MAX_TRUSTED_TEXT
            and _trusted_text_hash_matches(trusted_text, candidates[0].model_dump(), payload)
        ):
            result_metadata.update(
                {
                    "catalog_bound": True,
                    "judgment_request_context": dict(receipt),
                    "trusted_text": trusted_text,
                    "trusted_text_hash": EvidenceSpan.hash_text(trusted_text),
                }
            )
        return ProviderResult(
            status=ProviderResultStatus.FOUND if candidates else ProviderResultStatus.NOT_FOUND,
            provider_id=self.provider_id,
            candidates=candidates,
            coverage_complete=bool(coverage.get("coverage_complete")),
            metadata=result_metadata,
        )

    async def search(
        self,
        query: str = "",
        *,
        limit: int = 10,
        **kwargs: Any,
    ) -> ProviderResult:
        del kwargs
        if not isinstance(query, str) or not query.strip():
            return self._error(ProviderErrorCode.INVALID_IDENTIFIER, "SEARCH_TERM_REQUIRED")
        return self._call(
            "judgment_keyword_search",
            {"keyword": query.strip(), "top_k": max(1, min(limit, _MAX_RESULTS))},
        )

    def _local_lookup(self, identifier: str) -> ProviderResult:
        jid = OfficialJudgmentProvider.normalize_jid(identifier)
        if jid is None:
            jid = OfficialJudgmentProvider.normalize_partial_jid(identifier)
        if jid is None:
            return ProviderResult(
                status=ProviderResultStatus.NOT_FOUND,
                provider_id=self.provider_id,
                metadata={"local_portal": True, "candidate_only": True},
            )
        return self._call("judgment_lookup", {"jid": jid, "limit": 1})

    @staticmethod
    def _section_type(candidate: ProviderCandidate) -> EvidenceSectionType:
        role = str(candidate.metadata.get("section_role") or "").casefold()
        compact = role.replace("_", "")
        if "disposition" in compact:
            return EvidenceSectionType.DISPOSITION
        if "holding" in compact:
            return EvidenceSectionType.COURT_HOLDING
        if compact in {"reasoning", "courtreasoning"}:
            return EvidenceSectionType.COURT_REASONING
        if compact == "facts":
            return EvidenceSectionType.FACTS
        if compact == "procedure":
            return EvidenceSectionType.PROCEDURE
        return EvidenceSectionType.MIXED

    def _local_snapshot(
        self,
        result: ProviderResult,
        *,
        now: datetime,
    ) -> tuple[SourceRecord, list[EvidenceSpan]] | None:
        """Convert one catalog-bound local lookup into server-owned records."""

        if len(result.candidates) != 1 or result.metadata.get("catalog_bound") is not True:
            return None
        candidate = result.candidates[0]
        metadata = candidate.metadata
        trusted_text = result.metadata.get("trusted_text")
        source_hash = _canonical_sha256(metadata.get("source_hash"))
        jid = candidate.official_identifier
        if not (
            isinstance(jid, str)
            and jid
            and metadata.get("verification_status") == "catalog_bound"
            and metadata.get("local_verified") is True
            and metadata.get("citation_allowed") is True
            and metadata.get("registry_status") == "active"
            and _safe_identifier(metadata.get("catalog_artifact_id"))
            and _canonical_sha256(metadata.get("judgment_context_digest"))
            and source_hash
            and isinstance(trusted_text, str)
            and trusted_text.strip()
            and len(trusted_text) <= _MAX_TRUSTED_TEXT
            and _trusted_text_hash_matches(
                trusted_text,
                candidate.model_dump(mode="json"),
                result.metadata,
            )
        ):
            return None

        source_id = "src_local_judgment_" + hashlib.sha256(
            f"{jid}\x00{source_hash}".encode("utf-8")
        ).hexdigest()[:24]
        source = SourceRecord(
            source_id=source_id,
            source_key=f"judgment:{jid}",
            source_version_id=f"{jid}:{source_hash[7:23]}",
            material_type=MaterialType.JUDGMENT,
            provider_id=self.provider_id,
            source_tier=SourceTier.VERIFIED_CACHE,
            trust_status=TrustStatus.EVIDENCE_ELIGIBLE,
            official_identifier=jid,
            citation=candidate.title or jid,
            title=candidate.title,
            fetched_at=now,
            verified_at=now,
            expires_at=now + _LOCAL_SNAPSHOT_TTL,
            content_hash=source_hash,
            normalized_content_hash=source_hash,
            normalized_text=trusted_text,
            metadata={
                "retrieval": "local_catalog_verified_cache",
                "local_verified": True,
                "citation_allowed": True,
                "verification_status": "catalog_bound",
                "registry_status": "active",
                "catalog_artifact_id": metadata["catalog_artifact_id"],
                "judgment_context_digest": metadata["judgment_context_digest"],
                "source_hash": source_hash,
                "catalog_coverage_complete": bool(
                    (result.metadata.get("coverage") or {}).get("coverage_complete")
                    if isinstance(result.metadata.get("coverage"), Mapping)
                    else False
                ),
            },
        )
        provider_document_id = (
            candidate.identity.provider_document_id
            if candidate.identity is not None
            else None
        ) or jid
        evidence = EvidenceSpan.from_exact_text(
            evidence_id=(
                f"ev_{source_id}_"
                f"{hashlib.sha256(provider_document_id.encode('utf-8')).hexdigest()[:16]}"
            ),
            source_id=source_id,
            section_id=provider_document_id,
            section_type=self._section_type(candidate),
            exact_text=trusted_text,
            eligible_for_claim_support=True,
        )
        return source, [evidence]

    async def exact_lookup(
        self,
        identifier: str,
        *,
        now: datetime | None = None,
    ) -> tuple[ProviderResult, SourceRecord | None, list[EvidenceSpan]]:
        local = self._local_lookup(identifier)
        timestamp = now or datetime.now(UTC)
        local_snapshot = self._local_snapshot(local, now=timestamp)
        if local_snapshot is not None:
            local_source, local_evidence = local_snapshot
            return (
                ProviderResult(
                    status=ProviderResultStatus.FOUND,
                    provider_id=self.provider_id,
                    source_ids=[local_source.source_id],
                    evidence_ids=[item.evidence_id for item in local_evidence],
                    coverage_complete=local.coverage_complete,
                    metadata={
                        "local_portal": True,
                        "retrieval": "local_catalog_verified_cache",
                        "catalog_bound": True,
                        "verified_cache": True,
                        "coverage": local.metadata.get("coverage", {}),
                    },
                ),
                local_source,
                local_evidence,
            )

        official_result, source, evidence = await self.official_provider.exact_lookup(
            identifier,
            now=timestamp,
        )
        if official_result.status is ProviderResultStatus.FOUND and source is not None and evidence:
            return official_result, source, evidence
        if not local.candidates:
            return official_result, source, evidence
        metadata = {
            **official_result.metadata,
            "local_portal_candidate_only": True,
            "local_portal_lookup_status": local.status.value,
            "local_portal_candidate_count": len(local.candidates),
        }
        if official_result.status is ProviderResultStatus.FOUND:
            official_result = official_result.model_copy(
                update={
                    "status": ProviderResultStatus.PARTIAL,
                    "error_code": ProviderErrorCode.SOURCE_NOT_EVIDENCE_ELIGIBLE,
                    "message": "LOCAL_PORTAL_CANDIDATE_ONLY",
                    "metadata": metadata,
                }
            )
        else:
            official_result = official_result.model_copy(update={"metadata": metadata})
        return official_result.model_copy(update={"candidates": local.candidates}), source, evidence


def build_local_portal_judgment_provider(
    root: str | Path,
    *,
    official_provider: JudgmentProviderPort | None = None,
    portal: PortalCapabilityClient | None = None,
) -> LocalPortalJudgmentProvider:
    """Build an adapter from one explicit absolute local data root."""

    path = Path(root).expanduser()
    if not path.is_absolute():
        raise ValueError("local portal root must be absolute")
    return LocalPortalJudgmentProvider(
        path,
        official_provider=official_provider,
        portal=portal,
    )


def local_portal_root_from_env(environ: Mapping[str, str] | None = None) -> Path | None:
    env = os.environ if environ is None else environ
    value = env.get(LOCAL_PORTAL_ROOT_ENV, "").strip()
    if not value:
        return None
    path = Path(value).expanduser()
    if not path.is_absolute():
        raise ValueError("ALR_TW_LOCAL_PORTAL_ROOT must be an absolute path")
    return path


__all__ = [
    "LOCAL_PORTAL_PROVIDER_ID",
    "LOCAL_PORTAL_ROOT_ENV",
    "LocalPortalJudgmentProvider",
    "build_local_portal_judgment_provider",
    "local_portal_root_from_env",
]
