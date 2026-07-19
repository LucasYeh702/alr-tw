from __future__ import annotations

import pytest
from pydantic import ValidationError

from alr_tw.config.settings import CONFIG_MODE_REQUIRED, Settings
from alr_tw.contracts.providers import DataMode


def test_settings_default_to_synthetic_without_external_transfer():
    settings = Settings.from_env({})

    assert settings.data_mode is DataMode.SYNTHETIC
    assert settings.external_query_enabled is False
    assert settings.storage_policy.retention_seconds == 86400


def test_tlr_configuration_does_not_silently_enable_external_transfer():
    settings = Settings.from_env(
        {
            "ALR_TW_TLR_API_KEY": "synthetic-secret-value",
            "ALR_TW_TLR_BASE_URL": "https://tlr.example.test",
        }
    )

    assert settings.data_mode is DataMode.SYNTHETIC
    assert settings.external_query_enabled is False


def test_live_mode_must_be_explicit_when_live_features_are_required():
    settings = Settings.from_env({})

    with pytest.raises(ValueError, match=CONFIG_MODE_REQUIRED):
        settings.require_live_mode()


def test_hybrid_mode_enables_tlr_without_exposing_api_key():
    settings = Settings.from_env(
        {
            "ALR_TW_DATA_MODE": "hybrid_verified",
            "ALR_TW_RETENTION": "2h",
            "ALR_TW_TLR_API_KEY": "synthetic-secret-value",
        }
    )

    assert settings.data_mode is DataMode.HYBRID_VERIFIED
    assert settings.external_query_enabled is True
    assert settings.storage_policy.retention_seconds == 7200
    assert "synthetic-secret-value" not in repr(settings)
    assert "synthetic-secret-value" not in str(settings.model_dump())


def test_custom_tlr_endpoint_must_use_https_without_embedded_credentials():
    for endpoint in (
        "http://tlr.example.test",
        "https://user:password@tlr.example.test",
        "https://tlr.example.test/path#fragment",
    ):
        with pytest.raises(ValidationError):
            Settings.from_env(
                {
                    "ALR_TW_DATA_MODE": "hybrid_verified",
                    "ALR_TW_TLR_BASE_URL": endpoint,
                }
            )


@pytest.mark.parametrize("value", ["", "live", "yes", "HYBRID"])
def test_unknown_data_mode_is_rejected(value: str):
    with pytest.raises(ValidationError):
        Settings.from_env({"ALR_TW_DATA_MODE": value})


@pytest.mark.parametrize("value", ["0h", "-1h", "24", "forever"])
def test_invalid_retention_is_rejected(value: str):
    with pytest.raises((ValueError, ValidationError)):
        Settings.from_env({"ALR_TW_RETENTION": value})
