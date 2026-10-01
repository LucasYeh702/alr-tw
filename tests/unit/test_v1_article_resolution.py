"""Compound article locators must never silently resolve to their parent."""
import asyncio

import pytest

from alr_tw.contracts.providers import ProviderResultStatus
from alr_tw.providers.official.laws import OfficialLawProvider
from alr_tw.research.provider_executor import _LAW_CITATION
from test_v060_official_law_provider import FixtureTransport, _archive


@pytest.mark.parametrize('article', ['12條之1', '12之1條', '12-1條', '12 條 之 1'])
def test_compound_article_resolves_and_fetches_exact_source(article):
    provider = OfficialLawProvider(FixtureTransport(_archive()), verify_webpage=False)
    text = f'示範程序法第{article}第1項'
    pairs = asyncio.run(provider.resolve_citations(text))
    assert pairs == [('示範程序法', '12-1')]
    result, source, evidence = asyncio.run(provider.exact_lookup(*pairs[0]))
    assert result.status == ProviderResultStatus.FOUND
    assert source.official_identifier.endswith(':12-1')
    assert evidence is not None
    match = _LAW_CITATION.search(text)
    assert match is not None
    assert provider.normalize_article_no(match['article']) == '12-1'


@pytest.mark.parametrize('article', ['12條之', '12條之X', '12條之1之', '12條-1'])
def test_malformed_suffix_does_not_fall_back_to_parent(article):
    provider = OfficialLawProvider(FixtureTransport(_archive()), verify_webpage=False)
    text = f'示範程序法第{article}'
    assert asyncio.run(provider.resolve_citations(text)) == []
    assert _LAW_CITATION.search(text) is None


def test_missing_compound_article_is_not_parent_or_existing_sibling():
    provider = OfficialLawProvider(FixtureTransport(_archive()), verify_webpage=False)
    pairs = asyncio.run(provider.resolve_citations('示範程序法第12條之9'))
    assert pairs == [('示範程序法', '12-9')]
    result, source, evidence = asyncio.run(provider.exact_lookup(*pairs[0]))
    assert result.status == ProviderResultStatus.NOT_FOUND
    assert source is None and evidence is None
