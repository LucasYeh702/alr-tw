from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from alr_tw.config import Settings
from alr_tw.contracts.providers import (
    ProviderCapabilities,
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
from alr_tw.providers.local_portal import (
    LocalPortalJudgmentProvider,
    local_portal_root_from_env,
)
from alr_tw.research.provider_executor import ProviderObligationExecutor


DEMO_JID = "DEMO,130,測,1,20990101,1"
SECOND_DEMO_JID = "DEMO,130,測,2,20990102,1"


class FakePortal:
    def __init__(self, payload: dict, *, expected_capability: str = "judgment_keyword_search"):
        self.payload = payload
        self.expected_capability = expected_capability

    def call_capability(self, name: str, arguments: dict) -> dict:
        assert name == self.expected_capability
        if name == "judgment_keyword_search":
            assert arguments["top_k"] == 2
        return self.payload


class FakeOfficial:
    provider_id = "official_judicial_yuan_judgments"

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            exact_lookup=True,
            keyword_search=True,
            semantic_recall=False,
            official_verification=True,
            historical_versions=False,
            current_status_check=True,
            external_query_transfer=False,
        )

    async def health_check(self):
        raise AssertionError("health check is not part of this test")

    async def exact_lookup(self, identifier: str, *, now=None):
        return (
            ProviderResult(
                status=ProviderResultStatus.NOT_FOUND,
                provider_id=self.provider_id,
            ),
            None,
            [],
        )


class ExplodingOfficial(FakeOfficial):
    async def exact_lookup(self, identifier: str, *, now=None):
        raise AssertionError(f"official lookup should not run: {identifier}")


class FoundOfficial(FakeOfficial):
    async def exact_lookup(self, identifier: str, *, now=None):
        timestamp = now or datetime.now(UTC)
        text = "法院認定之工資計算理由。"
        text_hash = EvidenceSpan.hash_text(text)
        source = SourceRecord(
            source_id="src_official_judgment_fixture",
            source_key=f"judgment:{identifier}",
            source_version_id=f"{identifier}:fixture",
            material_type=MaterialType.JUDGMENT,
            provider_id=self.provider_id,
            source_tier=SourceTier.OFFICIAL,
            trust_status=TrustStatus.OFFICIAL_VERIFIED,
            official_identifier=identifier,
            citation="示範裁判",
            title="示範裁判",
            fetched_at=timestamp,
            verified_at=timestamp,
            expires_at=timestamp + timedelta(hours=1),
            content_hash=text_hash,
            normalized_content_hash=text_hash,
            normalized_text=text,
        )
        evidence = EvidenceSpan.from_exact_text(
            evidence_id="ev_official_judgment_fixture",
            source_id=source.source_id,
            section_id="reasoning-1",
            section_type=EvidenceSectionType.COURT_REASONING,
            exact_text=text,
            eligible_for_claim_support=True,
        )
        result = ProviderResult(
            status=ProviderResultStatus.FOUND,
            provider_id=self.provider_id,
            source_ids=[source.source_id],
            evidence_ids=[evidence.evidence_id],
            coverage_complete=True,
        )
        return result, source, [evidence]


class MismatchedFoundOfficial(FoundOfficial):
    async def exact_lookup(self, identifier: str, *, now=None):
        result, source, evidence = await super().exact_lookup(identifier, now=now)
        return result.model_copy(update={"provider_id": "unexpected-provider"}), source, evidence


def _catalog_receipt() -> dict[str, object]:
    receipt: dict[str, object] = {
        "schema": "taiwan-legal-portal.judgment-request-context/v1",
        "binding_status": "catalog_bound",
        "catalog_snapshot_id": "sha256:" + "a" * 64,
        "catalog_release_id": "coverage-test",
        "catalog_artifact_ids": ["judgment-test-01"],
        "registry_snapshot_id": "sha256:" + "b" * 64,
    }
    unsigned = json.dumps(
        receipt, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    receipt["context_digest"] = "sha256:" + hashlib.sha256(unsigned).hexdigest()
    return receipt


def _verified_lookup_payload() -> dict:
    text = "主文\n原判決關於工資之判斷。"
    return {
        "status": "success",
        "success": True,
        "found": True,
        "writes_performed": False,
        "coverage": {
            "coverage_complete": True,
            "binding_status": "catalog_bound",
            "catalog_snapshot_id": "sha256:" + "a" * 64,
            "catalog_release_id": "coverage-test",
        },
        "judgment_request_context": _catalog_receipt(),
        "trusted_text": text,
        "trusted_text_hash": "sha256:" + hashlib.sha256(text.encode()).hexdigest(),
        "results": [
            {
                "jid": DEMO_JID,
                "source_id": f"{DEMO_JID}#holding#1",
                "title": "工資給付",
                "section_role": "holding",
                "metadata": {
                    "verification_status": "catalog_bound",
                    "local_verified": True,
                    "citation_allowed": True,
                    "registry_status": "active",
                    "catalog_artifact_id": "judgment-test-01",
                    "source_hash": "sha256:" + "c" * 64,
                    "judgment_context_digest": "sha256:" + "d" * 64,
                },
            }
        ],
    }


def test_local_portal_root_requires_explicit_absolute_path():
    assert local_portal_root_from_env({}) is None
    assert local_portal_root_from_env({"ALR_TW_LOCAL_PORTAL_ROOT": "/tmp/legal"}) == Path(
        "/tmp/legal"
    )


def test_settings_resolves_hybrid_and_local_portal_root():
    settings = Settings.from_env(
        {
            "ALR_TW_DATA_MODE": "hybrid_verified",
            "ALR_TW_LOCAL_PORTAL_ROOT": "/tmp/legal",
            "ALR_TW_RETENTION": "1h",
        }
    )
    assert settings.external_query_enabled is True
    assert settings.local_portal_root == Path("/tmp/legal")


def test_local_search_is_candidate_only_and_keeps_write_boundary():
    provider = LocalPortalJudgmentProvider(
        Path("/tmp/legal"),
        official_provider=FakeOfficial(),
        portal=FakePortal(
            {
                "status": "success",
                "success": True,
                "found": True,
                "writes_performed": False,
                "mode": "local_fts",
                "coverage": {"coverage_complete": True},
                "results": [
                    {
                        "jid": DEMO_JID,
                        "source_id": f"{DEMO_JID}#reasoning#1",
                        "title": "損害賠償",
                        "snippet": "僅供候選的片段",
                    },
                    {
                        "jid": SECOND_DEMO_JID,
                        "source_id": f"{SECOND_DEMO_JID}#holding#1",
                        "title": "侵權行為",
                    },
                ],
            }
        ),
    )

    result = asyncio.run(provider.search("侵權行為", limit=2))

    assert result.status is ProviderResultStatus.FOUND
    assert len(result.candidates) == 2
    assert [candidate.official_identifier for candidate in result.candidates] == [
        DEMO_JID,
        SECOND_DEMO_JID,
    ]
    first_identity = result.candidates[0].identity
    assert first_identity is not None
    assert first_identity.canonical_jid == DEMO_JID
    assert first_identity.provider_document_id == f"{DEMO_JID}#reasoning#1"
    assert all(candidate.metadata["candidate_only"] for candidate in result.candidates)
    assert all(candidate.metadata["snippet_only"] for candidate in result.candidates)
    assert result.evidence_ids == []


def test_invalid_write_flag_fails_closed():
    provider = LocalPortalJudgmentProvider(
        Path("/tmp/legal"),
        official_provider=FakeOfficial(),
        portal=FakePortal(
            {
                "status": "success",
                "success": True,
                "found": False,
                "writes_performed": True,
                "results": [],
            }
        ),
    )

    result = asyncio.run(provider.search("侵權行為", limit=2))

    assert result.status is ProviderResultStatus.ERROR
    assert result.error_code.value == "EXTERNAL_PROVIDER_SCHEMA_CHANGED"


def test_exact_lookup_promotes_catalog_bound_local_snapshot_to_evidence():
    provider = LocalPortalJudgmentProvider(
        Path("/tmp/legal"),
        official_provider=ExplodingOfficial(),
        portal=FakePortal(
            _verified_lookup_payload(), expected_capability="judgment_lookup"
        ),
    )

    result, source, evidence = asyncio.run(
        provider.exact_lookup(DEMO_JID, now=datetime(2040, 1, 1, tzinfo=UTC))
    )
    later_result, later_source, later_evidence = asyncio.run(
        provider.exact_lookup(
            DEMO_JID,
            now=datetime(2040, 1, 1, tzinfo=UTC) + timedelta(seconds=1),
        )
    )

    assert result.status is ProviderResultStatus.FOUND
    assert result.metadata["verified_cache"] is True
    assert source is not None
    assert source.source_tier.value == "verified_cache"
    assert source.trust_status.value == "evidence_eligible"
    assert source.official_identifier == DEMO_JID
    assert len(evidence) == 1
    assert evidence[0].section_type.value == "court_holding"
    assert evidence[0].verify_text(evidence[0].exact_text)
    assert later_result.provider_id == provider.provider_id
    assert later_source is not None
    assert later_source.source_id != source.source_id
    assert later_evidence[0].source_id == later_source.source_id
    assert later_evidence[0].evidence_id != evidence[0].evidence_id


def test_exact_lookup_fails_closed_when_trusted_text_hash_is_tampered():
    payload = _verified_lookup_payload()
    payload["trusted_text_hash"] = "sha256:" + "e" * 64
    provider = LocalPortalJudgmentProvider(
        Path("/tmp/legal"),
        official_provider=FakeOfficial(),
        portal=FakePortal(payload, expected_capability="judgment_lookup"),
    )

    result, source, evidence = asyncio.run(
        provider.exact_lookup(DEMO_JID)
    )

    assert source is None
    assert evidence == []
    assert result.metadata["local_portal_candidate_only"] is True


def test_official_fallback_is_rebound_to_local_adapter_before_contract_validation():
    payload = _verified_lookup_payload()
    payload["trusted_text_hash"] = "sha256:" + "e" * 64
    provider = LocalPortalJudgmentProvider(
        Path.cwd() / "synthetic-root",
        official_provider=FoundOfficial(),
        portal=FakePortal(payload, expected_capability="judgment_lookup"),
    )

    result, source, evidence = asyncio.run(provider.exact_lookup(DEMO_JID))

    assert source is not None
    assert result.provider_id == provider.provider_id
    assert source.provider_id == provider.provider_id
    assert result.metadata["delegated_provider_id"] == FoundOfficial.provider_id
    assert source.metadata["delegated_provider_id"] == FoundOfficial.provider_id
    assert result.metadata["delegated_source_id"] == "src_official_judgment_fixture"
    assert source.source_id != result.metadata["delegated_source_id"]
    assert result.source_ids == [source.source_id]
    assert result.evidence_ids == [item.evidence_id for item in evidence]
    assert all(item.source_id == source.source_id for item in evidence)
    assert result.metadata["delegated_evidence_ids"] == [
        "ev_official_judgment_fixture"
    ]
    validated, validated_source, validated_evidence = (
        ProviderObligationExecutor._validated_exact_material(
            result,
            source,
            evidence,
            expected_provider_id=provider.provider_id,
        )
    )
    assert validated.status is ProviderResultStatus.FOUND
    assert validated_source is source
    assert validated_evidence == evidence


def test_unexpected_official_provider_identity_is_still_rejected():
    payload = _verified_lookup_payload()
    payload["trusted_text_hash"] = "sha256:" + "e" * 64
    provider = LocalPortalJudgmentProvider(
        Path.cwd() / "synthetic-root",
        official_provider=MismatchedFoundOfficial(),
        portal=FakePortal(payload, expected_capability="judgment_lookup"),
    )

    result, source, evidence = asyncio.run(provider.exact_lookup(DEMO_JID))
    validated, validated_source, validated_evidence = (
        ProviderObligationExecutor._validated_exact_material(
            result,
            source,
            evidence,
            expected_provider_id=provider.provider_id,
        )
    )

    assert validated.error_code.value == "PROVIDER_RESULT_CONTRACT_VIOLATION"
    assert validated_source is None
    assert validated_evidence == []


def test_exact_lookup_preserves_official_not_found_when_portal_is_unavailable():
    provider = LocalPortalJudgmentProvider(
        Path("/tmp/legal"),
        official_provider=FakeOfficial(),
        load_error="PORTAL_PACKAGE_UNAVAILABLE",
    )

    result, source, evidence = asyncio.run(provider.exact_lookup(DEMO_JID))

    assert result.status is ProviderResultStatus.NOT_FOUND
    assert result.provider_id == FakeOfficial.provider_id
    assert result.candidates == []
    assert source is None
    assert evidence == []


def test_reverified_local_and_fallback_snapshots_coexist_in_storage(tmp_path):
    from alr_tw.research.service import ResearchService
    from alr_tw.storage.sqlite_store import SqliteStore
    from alr_tw.contracts.providers import DataMode
    store = SqliteStore(tmp_path / 'cache')
    service = ResearchService(store)
    run = service.create_run('合成快照持久化', mode=DataMode.SYNTHETIC)
    timestamp = datetime.now(UTC)
    for fallback in (False, True):
        payload = _verified_lookup_payload()
        if fallback:
            payload['trusted_text_hash'] = 'sha256:' + 'e' * 64
        provider = LocalPortalJudgmentProvider(
            Path.cwd() / 'synthetic-root', official_provider=FoundOfficial(),
            portal=FakePortal(payload, expected_capability='judgment_lookup'))
        identities = []
        for offset in (0, 1):
            result, source, evidence = asyncio.run(provider.exact_lookup(
                DEMO_JID, now=timestamp + timedelta(seconds=offset)))
            checked, source, evidence = ProviderObligationExecutor._validated_exact_material(
                result, source, evidence, expected_provider_id=provider.provider_id)
            assert checked.status is ProviderResultStatus.FOUND and source is not None
            store.save_source(run.run_id, source)
            for span in evidence:
                store.save_evidence(run.run_id, span)
            identities.append(source.source_id)
        assert identities[0] != identities[1]
    assert len(store.list_sources(run.run_id)) == 4
    assert len(store.list_evidence(run.run_id)) == 4
