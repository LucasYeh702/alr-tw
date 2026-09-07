"""Single source of truth for MCP tool ownership and profile exposure."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterable

from alr_tw.contracts.providers import ToolProfile


class ToolCategory(str, Enum):
    SERVER_OWNED = "server_owned"
    LEGACY_COMPATIBILITY = "legacy_compatibility"
    SYNTHETIC_DEMO = "synthetic_demo"


@dataclass(frozen=True)
class ToolCatalogEntry:
    name: str
    category: ToolCategory
    alternatives: tuple[str, ...] = ()


TOOL_CATALOG: tuple[ToolCatalogEntry, ...] = (
    ToolCatalogEntry("get_legal_research_capabilities", ToolCategory.SERVER_OWNED),
    ToolCatalogEntry("research_legal_question", ToolCategory.SERVER_OWNED),
    ToolCatalogEntry("execute_legal_research", ToolCategory.SERVER_OWNED),
    ToolCatalogEntry("submit_legal_research_plan", ToolCategory.SERVER_OWNED),
    ToolCatalogEntry("continue_legal_research", ToolCategory.SERVER_OWNED),
    ToolCatalogEntry("get_legal_research_state", ToolCategory.SERVER_OWNED),
    ToolCatalogEntry("get_legal_research_finalization", ToolCategory.SERVER_OWNED),
    ToolCatalogEntry("lookup_legal_source", ToolCategory.SERVER_OWNED),
    ToolCatalogEntry("inspect_judgment_lineage", ToolCategory.SERVER_OWNED),
    ToolCatalogEntry("lookup_legislative_history", ToolCategory.SERVER_OWNED),
    ToolCatalogEntry("validate_legal_analysis", ToolCategory.SERVER_OWNED),
    ToolCatalogEntry("validate_legal_answer", ToolCategory.SERVER_OWNED),
    ToolCatalogEntry("purge_research_storage", ToolCategory.SERVER_OWNED),
    ToolCatalogEntry(
        "agentic_legal_research",
        ToolCategory.SYNTHETIC_DEMO,
        ("research_legal_question",),
    ),
    ToolCatalogEntry(
        "legal_search",
        ToolCategory.SYNTHETIC_DEMO,
        ("lookup_legal_source", "research_legal_question"),
    ),
    ToolCatalogEntry(
        "begin_agentic_run",
        ToolCategory.LEGACY_COMPATIBILITY,
        ("research_legal_question",),
    ),
    ToolCatalogEntry(
        "finalize_agentic_run",
        ToolCategory.LEGACY_COMPATIBILITY,
        ("validate_legal_answer",),
    ),
    ToolCatalogEntry(
        "run_agentic_demo",
        ToolCategory.SYNTHETIC_DEMO,
        ("research_legal_question",),
    ),
    ToolCatalogEntry(
        "build_validation_report",
        ToolCategory.SYNTHETIC_DEMO,
        ("validate_legal_answer",),
    ),
    ToolCatalogEntry(
        "get_claim_grounding_policy",
        ToolCategory.LEGACY_COMPATIBILITY,
        ("validate_legal_answer",),
    ),
    ToolCatalogEntry(
        "extract_answer_claims",
        ToolCategory.LEGACY_COMPATIBILITY,
        ("validate_legal_answer",),
    ),
    ToolCatalogEntry(
        "check_claim_support",
        ToolCategory.LEGACY_COMPATIBILITY,
        ("validate_legal_answer",),
    ),
    ToolCatalogEntry(
        "get_trust_model",
        ToolCategory.LEGACY_COMPATIBILITY,
        ("get_legal_research_capabilities",),
    ),
    ToolCatalogEntry(
        "validate_citation",
        ToolCategory.LEGACY_COMPATIBILITY,
        ("lookup_legal_source", "validate_legal_answer"),
    ),
    ToolCatalogEntry(
        "exact_law_lookup",
        ToolCategory.SYNTHETIC_DEMO,
        ("lookup_legal_source",),
    ),
    ToolCatalogEntry(
        "exact_judgment_lookup",
        ToolCategory.SYNTHETIC_DEMO,
        ("lookup_legal_source",),
    ),
    ToolCatalogEntry(
        "exact_constitutional_lookup",
        ToolCategory.SYNTHETIC_DEMO,
        ("lookup_legal_source",),
    ),
)

TOOL_CATALOG_BY_NAME = {entry.name: entry for entry in TOOL_CATALOG}
SERVER_OWNED_TOOL_NAMES = frozenset(
    entry.name for entry in TOOL_CATALOG if entry.category is ToolCategory.SERVER_OWNED
)

_PROFILE_CATEGORIES = {
    ToolProfile.VERIFIED: frozenset({ToolCategory.SERVER_OWNED}),
    ToolProfile.COMPATIBILITY: frozenset(
        {ToolCategory.SERVER_OWNED, ToolCategory.LEGACY_COMPATIBILITY}
    ),
    ToolProfile.DEMO: frozenset(ToolCategory),
}


def get_tool_catalog() -> tuple[ToolCatalogEntry, ...]:
    """Return the immutable ordered catalog used by discovery and invocation."""
    return TOOL_CATALOG


def resolve_tool_profile(profile: ToolProfile | str) -> ToolProfile:
    if isinstance(profile, ToolProfile):
        return profile
    try:
        return ToolProfile(profile)
    except (TypeError, ValueError) as exc:
        allowed = ", ".join(item.value for item in ToolProfile)
        raise ValueError(f"ALR_TW_MCP_TOOL_PROFILE must be one of: {allowed}") from exc


def tool_names_for_profile(profile: ToolProfile | str) -> tuple[str, ...]:
    resolved = resolve_tool_profile(profile)
    categories = _PROFILE_CATEGORIES[resolved]
    return tuple(entry.name for entry in TOOL_CATALOG if entry.category in categories)


def tool_is_available(name: str, profile: ToolProfile | str) -> bool:
    resolved = resolve_tool_profile(profile)
    entry = TOOL_CATALOG_BY_NAME.get(name)
    return entry is not None and entry.category in _PROFILE_CATEGORIES[resolved]


def filter_tool_definitions(
    definitions: Iterable[dict[str, Any]],
    profile: ToolProfile | str,
) -> list[dict[str, Any]]:
    """Filter and classify definitions without allowing an unlisted tool to run."""
    resolved = resolve_tool_profile(profile)
    source = list(definitions)
    names = [definition.get("name") for definition in source]
    catalog_names = set(TOOL_CATALOG_BY_NAME)
    if len(names) != len(set(names)) or set(names) != catalog_names:
        raise RuntimeError("MCP tool definitions do not match the tool catalog")

    allowed = set(tool_names_for_profile(resolved))
    return [
        _with_profile_description(dict(definition))
        for definition in source
        if definition["name"] in allowed
    ]


def unavailable_tool_details(name: str, profile: ToolProfile | str) -> dict[str, Any]:
    resolved = resolve_tool_profile(profile)
    entry = TOOL_CATALOG_BY_NAME.get(name)
    if entry is None:
        raise KeyError(name)
    return {
        "tool_name": entry.name,
        "profile": resolved.value,
        "category": entry.category.value,
        "alternative_tools": list(entry.alternatives),
    }


def unavailable_tool_message(name: str, profile: ToolProfile | str) -> str:
    details = unavailable_tool_details(name, profile)
    alternatives = ", ".join(details["alternative_tools"]) or "server-owned research tools"
    return (
        f"Tool '{name}' is not available in MCP profile '{details['profile']}'. "
        f"Use an available server-owned alternative: {alternatives}."
    )


def _with_profile_description(definition: dict[str, Any]) -> dict[str, Any]:
    entry = TOOL_CATALOG_BY_NAME[definition["name"]]
    description = str(definition.get("description", ""))
    if entry.category is ToolCategory.SYNTHETIC_DEMO:
        marker = "[DEMO ONLY]"
        redirect = (
            "Synthetic fixtures are for demonstration only; use lookup_legal_source or "
            "research_legal_question for formal server-owned research."
        )
    elif entry.category is ToolCategory.LEGACY_COMPATIBILITY:
        marker = "[LEGACY COMPATIBILITY]"
        redirect = (
            "Retained for v0.9.1 compatibility; prefer the corresponding server-owned "
            "research or answer-validation tool."
        )
    else:
        return definition

    if not description.startswith(marker):
        definition["description"] = f"{marker} {redirect}\n{description}"
    return definition
