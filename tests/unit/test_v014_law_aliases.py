import asyncio
import io
import json
import zipfile

import pytest

from alr_tw.contracts.providers import ProviderResultStatus
from alr_tw.providers.official.law_aliases import LAW_ALIASES, resolve_law_name
from alr_tw.providers.official.laws import OfficialLawProvider
from test_v060_official_law_provider import FixtureTransport, _archive


def provider_with_names(names):
    with zipfile.ZipFile(io.BytesIO(_archive())) as archive:
        doc = json.loads(archive.read("ChLaw.json"))
    template = doc["Laws"][0]
    doc["Laws"] = [dict(template, LawName=name) for name in names]
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr("ChLaw.json", json.dumps(doc))
    return OfficialLawProvider(FixtureTransport(stream.getvalue()), verify_webpage=False)


@pytest.mark.parametrize("alias,canonical", list(LAW_ALIASES.items()))
def test_alias_still_requires_catalog_and_exact_article(alias, canonical):
    provider = provider_with_names([canonical])
    result, source, evidence = asyncio.run(provider.exact_lookup(alias, "12-1"))
    assert result.status == ProviderResultStatus.FOUND
    assert source.title == canonical and evidence.exact_text
    assert result.metadata["name_resolution"]["official_name"] == canonical
    assert asyncio.run(provider.resolve_citations(alias + "第12-1條")) == [(canonical, "12-1")]
    search = asyncio.run(provider.search(alias))
    assert search.metadata["matches"][0]["law_name"] == canonical
    missing, source, _ = asyncio.run(provider.exact_lookup(alias, "999"))
    assert missing.status == ProviderResultStatus.NOT_FOUND and source is None
    unavailable = provider_with_names(["示範程序法"])
    assert asyncio.run(unavailable.resolve_citations(alias + "第1條")) == []
    missing, _, _ = asyncio.run(unavailable.exact_lookup(alias, "12-1"))
    assert missing.status == ProviderResultStatus.NOT_FOUND


def test_official_names_win_and_ambiguous_aliases_are_not_guessed():
    assert resolve_law_name("勞基法", {"勞基法", "勞動基準法"}) == ("勞基法", {})
    for name in ["家事法", "智保法", "公司法"]:
        assert resolve_law_name(name, set(LAW_ALIASES.values())) == (name, {})
    provider = provider_with_names(["勞基法", "勞動基準法", "合成勞基法"])
    assert asyncio.run(provider.resolve_citations("合成勞基法第1條")) == [("合成勞基法", "1")]
    with pytest.raises(TypeError):
        LAW_ALIASES["家事法"] = "猜測"
