"""Normalize MCP transport metadata before strict business validation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True, slots=True)
class NormalizedToolCall:
    """A tool call with reserved host metadata separated from arguments."""

    name: str
    arguments: dict[str, Any]
    request_meta: Mapping[str, Any] | None
    compatibility_meta: Mapping[str, Any] | None


def normalize_call_tool_params(params: Mapping[str, Any]) -> NormalizedToolCall:
    """Remove only the two MCP-reserved top-level metadata locations.

    Nested ``_meta`` values remain business data and are deliberately left for
    each tool's strict input validator.
    """

    if not isinstance(params, Mapping):
        raise ValueError("INVALID_TOOL_ARGUMENTS: tool call params must be an object")

    normalized = dict(params)
    request_meta = normalized.pop("_meta", None)
    _validate_meta_shape(request_meta)
    _reject_unexpected_keys(normalized, {"name", "arguments"})

    name = normalized.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ValueError("INVALID_TOOL_ARGUMENTS: name is required")

    raw_arguments = normalized.get("arguments") or {}
    if not isinstance(raw_arguments, Mapping):
        raise ValueError("INVALID_TOOL_ARGUMENTS: tool arguments must be an object")
    arguments = dict(raw_arguments)
    compatibility_meta = arguments.pop("_meta", None)
    _validate_meta_shape(compatibility_meta)

    return NormalizedToolCall(
        name=name.strip(),
        arguments=arguments,
        request_meta=request_meta,
        compatibility_meta=compatibility_meta,
    )


def _validate_meta_shape(value: Any) -> None:
    if value is not None and not isinstance(value, Mapping):
        raise ValueError("INVALID_TOOL_ARGUMENTS: _meta must be an object")


def _reject_unexpected_keys(arguments: Mapping[str, Any], allowed: set[str]) -> None:
    unexpected = sorted(set(arguments) - allowed)
    if unexpected:
        raise ValueError(
            "INVALID_TOOL_ARGUMENTS: unexpected arguments: " + ", ".join(unexpected)
        )
