"""Fail-closed environment configuration for the v0.10.0 preview."""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator, model_validator

from alr_tw.contracts.providers import DataMode, ToolProfile
from alr_tw.contracts.storage import StoragePolicy

CONFIG_MODE_REQUIRED = "CONFIG_MODE_REQUIRED"
ALR_TW_MCP_TOOL_PROFILE = "ALR_TW_MCP_TOOL_PROFILE"
_RETENTION_PATTERN = re.compile(r"^(?P<count>[1-9][0-9]*)(?P<unit>[smhd])$")
_UNIT_SECONDS = {"s": 1, "m": 60, "h": 3600, "d": 86400}


def parse_retention(value: str) -> int:
    match = _RETENTION_PATTERN.fullmatch(value.strip().lower())
    if match is None:
        raise ValueError("ALR_TW_RETENTION must use a positive duration such as 24h")
    seconds = int(match.group("count")) * _UNIT_SECONDS[match.group("unit")]
    if seconds > 7 * 24 * 60 * 60:
        raise ValueError("ALR_TW_RETENTION cannot exceed 7d in the public preview")
    return seconds


class Settings(BaseModel):
    """Resolved settings; MCP profile defaults are derived from data mode."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    data_mode: DataMode = DataMode.SYNTHETIC
    mcp_tool_profile: ToolProfile = ToolProfile.DEMO
    storage_policy: StoragePolicy = Field(default_factory=StoragePolicy)
    storage_path: Path | None = None
    tlr_base_url: str = "https://tlr.dr-lawbot.com"
    tlr_api_key: SecretStr | None = Field(default=None, exclude=True, repr=False)

    @model_validator(mode="before")
    @classmethod
    def default_mcp_tool_profile(cls, value: Any) -> Any:
        if not isinstance(value, Mapping):
            return value
        values = dict(value)
        if values.get("mcp_tool_profile") is not None:
            return values
        try:
            mode = DataMode(values.get("data_mode", DataMode.SYNTHETIC))
        except (TypeError, ValueError):
            # Let Pydantic report the existing data-mode validation error.
            return values
        values["mcp_tool_profile"] = (
            ToolProfile.DEMO if mode is DataMode.SYNTHETIC else ToolProfile.VERIFIED
        )
        return values

    @field_validator("tlr_base_url")
    @classmethod
    def validate_tlr_base_url(cls, value: str) -> str:
        parsed = urlsplit(value)
        if parsed.scheme != "https" or not parsed.hostname:
            raise ValueError("TLR base URL must be an absolute HTTPS URL")
        if parsed.username is not None or parsed.password is not None:
            raise ValueError("TLR base URL must not contain credentials")
        if parsed.fragment:
            raise ValueError("TLR base URL must not contain a fragment")
        return value.rstrip("/")

    @property
    def external_query_enabled(self) -> bool:
        return self.data_mode is DataMode.HYBRID_VERIFIED

    @property
    def tool_profile(self) -> ToolProfile:
        """Alias used by MCP session code without coupling it to the env name."""
        return self.mcp_tool_profile

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> Settings:
        env = os.environ if environ is None else environ
        mode_value = env.get("ALR_TW_DATA_MODE", DataMode.SYNTHETIC.value)
        retention = parse_retention(env.get("ALR_TW_RETENTION", "24h"))
        storage_path = env.get("ALR_TW_STORAGE_PATH") or None
        configured_key = env.get("ALR_TW_TLR_API_KEY") or None
        values = {
            "data_mode": mode_value,
            "storage_policy": StoragePolicy(retention_seconds=retention),
            "storage_path": Path(storage_path).expanduser() if storage_path else None,
            "tlr_base_url": env.get("ALR_TW_TLR_BASE_URL", "https://tlr.dr-lawbot.com"),
            "tlr_api_key": SecretStr(configured_key) if configured_key else None,
        }
        configured_profile = env.get(ALR_TW_MCP_TOOL_PROFILE)
        if configured_profile is not None:
            values["mcp_tool_profile"] = configured_profile
        return cls.model_validate(values)

    def require_live_mode(self) -> None:
        if self.data_mode is DataMode.SYNTHETIC:
            raise ValueError(f"{CONFIG_MODE_REQUIRED}: select official_only or hybrid_verified")
