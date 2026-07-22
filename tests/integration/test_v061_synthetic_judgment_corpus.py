from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path

from alr_tw.contracts.providers import ProviderResultStatus
from alr_tw.contracts.sources import EvidenceSectionType
from alr_tw.providers.official import OfficialJudgmentProvider
from alr_tw.providers.official.judicial_site import JudicialSiteResponse


FIXTURE_DIR = Path(__file__).parents[1] / "fixtures" / "judgments" / "v061"


class FixtureTransport:
    def __init__(self, document: bytes) -> None:
        self.document = document

    async def open(self) -> None:
        return None

    async def close(self) -> None:
        return None

    async def get(self, url: str, *, timeout: float, max_bytes: int) -> JudicialSiteResponse:
        del timeout, max_bytes
        return JudicialSiteResponse(200, self.document, {}, url)

    async def post_form(self, *args, **kwargs):  # pragma: no cover - exact lookup only
        raise AssertionError("search must not be used by this fixture test")


def test_synthetic_layout_corpus_preserves_all_sources_and_role_safety() -> None:
    manifest = json.loads((FIXTURE_DIR / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["satisfies_ordinary_court_release_gate"] is False
    assert len(manifest["cases"]) == 8

    source_count = 0
    false_promotions = 0
    partial_count = 0
    for case in manifest["cases"]:
        document = (FIXTURE_DIR / case["fixture_file"]).read_bytes()
        assert hashlib.sha256(document).hexdigest() == case["sha256"]
        provider = OfficialJudgmentProvider(FixtureTransport(document))

        result, source, evidence = asyncio.run(provider.exact_lookup(case["canonical_jid"]))

        assert result.status is ProviderResultStatus.FOUND
        assert source is not None
        assert source.official_identifier == case["canonical_jid"]
        assert source.metadata["parse_status"] == case["expected_parse_status"]
        source_count += 1
        partial_count += int(source.metadata["parse_status"] == "partial")
        eligible_reasoning = [
            item
            for item in evidence
            if item.eligible_for_claim_support
            and item.section_type
            in {EvidenceSectionType.COURT_REASONING, EvidenceSectionType.COURT_HOLDING}
        ]
        assert len(eligible_reasoning) >= case["expected_min_eligible_reasoning_spans"]
        false_promotions += sum(
            item.eligible_for_claim_support
            for item in evidence
            if item.section_type is EvidenceSectionType.PARTY_ARGUMENT
        )

    assert source_count == 8
    assert partial_count == 2
    assert false_promotions == 0
