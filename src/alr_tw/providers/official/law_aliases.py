"""Reviewed contemporary display aliases; never a historical-version resolver."""

from types import MappingProxyType

ALIAS_VERSION = "alr-tw.law-aliases/v1"
LAW_ALIASES = MappingProxyType({
    "勞基法": "勞動基準法",
    "消保法": "消費者保護法",
    "個資法": "個人資料保護法",
    "證交法": "證券交易法",
})


def resolve_law_name(name: str, official_names: set[str]) -> tuple[str, dict[str, str]]:
    original = name.strip()
    if original in official_names:
        return original, {}
    canonical = LAW_ALIASES.get(original)
    if canonical and canonical in official_names:
        return canonical, {"input_name": original, "official_name": canonical,
                           "rule_version": ALIAS_VERSION}
    return original, {}
