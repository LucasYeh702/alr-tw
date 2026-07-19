"""Fail-closed environment configuration for v0.6 live data modes."""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from pathlib import Path
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator

from alr_tw.contracts.providers import DataMode
from alr_tw.contracts.storage import StoragePolicy

CONFIG_MODE_REQUIRED = "CONFIG_MODE_REQUIRED"
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
    """Resolved settings; synthetic mode is the only implicit default."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    data_mode: DataMode = DataMode.SYNTHETIC
    storage_policy: StoragePolicy = Field(default_factory=StoragePolicy)
    storage_path: Path | None = None
    tlr_base_url: str = "https://tlr.dr-lawbot.com"
    tlr_api_key: SecretStr | None = Field(default=None, exclude=True, repr=False)

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

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> Settings:
        env = os.environ if environ is None else environ
        mode_value = env.get("ALR_TW_DATA_MODE", DataMode.SYNTHETIC.value)
        retention = parse_retention(env.get("ALR_TW_RETENTION", "24h"))
        storage_path = env.get("ALR_TW_STORAGE_PATH") or None
        configured_key = env.get("ALR_TW_TLR_API_KEY") or None
        return cls.model_validate(
            {
                "data_mode": mode_value,
                "storage_policy": StoragePolicy(retention_seconds=retention),
                "storage_path": Path(storage_path).expanduser() if storage_path else None,
                "tlr_base_url": env.get(
                    "ALR_TW_TLR_BASE_URL", "https://tlr.dr-lawbot.com"
                ),
                "tlr_api_key": SecretStr(configured_key) if configured_key else None,
            }
        )

    def require_live_mode(self) -> None:
        if self.data_mode is DataMode.SYNTHETIC:
            raise ValueError(f"{CONFIG_MODE_REQUIRED}: select official_only or hybrid_verified")
