from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Protocol

from .verification.answer_validation import answer_with_validation
from .verification.citation_validator import validate_citation
from .verification.trust_gates import evaluate_trust_gate


@dataclass(frozen=True)
class SourceManifest:
    provider: str
    dataset_name: str
    dataset_version: str
    source_url: str
    license_name: str
    attribution_text: str
    retrieved_at: str
    source_tier: str
    redistribution_allowed: bool
    schema: str = "alr-tw.source-manifest/v1"
    terms_reviewed_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class AdapterResult:
    adapter_name: str
    status: str
    manifest: SourceManifest
    records: list[dict[str, Any]]
    schema: str = "alr-tw.adapter-result/v1"
    error_code: str = ""
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RetrievalCandidate:
    citation_id: str
    source_id: str
    source_tier: str
    title: str
    snippet: str
    score: float
    manifest_id: str
    official_url: str = ""
    official_identifier: str = ""
    official_hash: str = ""
    verified_at: str = ""
    jid: str = ""
    schema: str = "alr-tw.retrieval-candidate/v1"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class SourceAdapter(Protocol):
    def load(self) -> AdapterResult:
        ...


class Retriever(Protocol):
    def search(self, query: str, adapter_result: AdapterResult) -> list[RetrievalCandidate]:
        ...


class CitationVerifier(Protocol):
    def verify(self, candidate: RetrievalCandidate, *, require_final: bool) -> dict[str, Any]:
        ...


class SyntheticOfficialAdapter:
    """Synthetic implementation of the public adapter contract.

    The shape mirrors a production adapter, but the data is intentionally fake.
    """

    def load(self) -> AdapterResult:
        manifest = SourceManifest(
            provider="Synthetic Official Source",
            dataset_name="synthetic-civil-law-demo",
            dataset_version="v0.2",
            source_url="https://example.test/synthetic-official/civil-law-demo",
            license_name="Synthetic demo fixture",
            attribution_text="Synthetic demo data generated for this reference repository.",
            retrieved_at="2026-01-01T00:00:00Z",
            terms_reviewed_at="2026-01-01T00:00:00Z",
            source_tier="official",
            redistribution_allowed=True,
        )
        records = [
            {
                "citation_id": "official-demo-law-184",
                "source_id": "official-demo-law-184",
                "source_tier": "official",
                "title": "Synthetic Civil Code Article 184",
                "text": "Synthetic official-grounded fixture for tort and lease-deposit discussion.",
                "official_url": f"{manifest.source_url}#article-184",
                "official_hash": "sha256:synthetic-official-law-184",
                "verified_at": manifest.retrieved_at,
                "manifest_id": manifest.dataset_name,
            },
            {
                "citation_id": "tlr-candidate-demo-001",
                "source_id": "tlr-candidate-demo-001",
                "source_tier": "external_semantic_recall",
                "title": "Synthetic TLR Candidate",
                "text": "Synthetic candidate-only judgment lead. It must be verified elsewhere.",
                "jid": "DEMO,113,測,1,20990101,1",
                "manifest_id": manifest.dataset_name,
            },
        ]
        return AdapterResult(
            adapter_name="synthetic_official_adapter",
            status="loaded",
            manifest=manifest,
            records=records,
        )


class SyntheticRetriever:
    def search(self, query: str, adapter_result: AdapterResult) -> list[RetrievalCandidate]:
        candidates: list[RetrievalCandidate] = []
        for index, record in enumerate(adapter_result.records):
            text = f"{record.get('title', '')} {record.get('text', '')}"
            if "184" not in query and "押金" not in query and "deposit" not in query.lower():
                continue
            candidates.append(
                RetrievalCandidate(
                    citation_id=str(record["citation_id"]),
                    source_id=str(record["source_id"]),
                    source_tier=str(record["source_tier"]),
                    title=str(record.get("title") or ""),
                    snippet=text[:120],
                    score=1.0 - (index * 0.1),
                    manifest_id=str(record.get("manifest_id") or adapter_result.manifest.dataset_name),
                    official_url=str(record.get("official_url") or ""),
                    official_identifier=str(record.get("official_identifier") or ""),
                    official_hash=str(record.get("official_hash") or ""),
                    verified_at=str(record.get("verified_at") or ""),
                    jid=str(record.get("jid") or ""),
                )
            )
        return candidates


class SourcePolicyCitationVerifier:
    def verify(self, candidate: RetrievalCandidate, *, require_final: bool) -> dict[str, Any]:
        return validate_citation(candidate.to_dict(), require_final=require_final)


def run_synthetic_contract_pipeline(query: str) -> dict[str, Any]:
    adapter = SyntheticOfficialAdapter()
    adapter_result = adapter.load()
    candidates = SyntheticRetriever().search(query, adapter_result)
    verifier = SourcePolicyCitationVerifier()
    verifications = [verifier.verify(candidate, require_final=True) for candidate in candidates]
    final_citations = [
        candidate.to_dict()
        for candidate, verification in zip(candidates, verifications, strict=True)
        if verification["citation_use"] == "allow_final"
    ]
    answer = "Synthetic answer guarded by official-grounded citation validation."
    coverage = {"has_laws": "present", "has_judgments": "not_checked"}
    trust_gate = evaluate_trust_gate(answer=answer, citations=final_citations, coverage=coverage)
    answer_validation = answer_with_validation(answer, final_citations)

    return {
        "schema": "alr-tw.synthetic-contract-pipeline/v1",
        "source_manifest": adapter_result.manifest.to_dict(),
        "adapter_result": adapter_result.to_dict(),
        "retrieval_candidates": [candidate.to_dict() for candidate in candidates],
        "citation_verifications": verifications,
        "final_citations": final_citations,
        "trust_gate": trust_gate,
        "answer_validation": answer_validation["validation_summary"],
    }
