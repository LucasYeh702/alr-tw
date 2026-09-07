"""ALR-TW operational CLI."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any, Sequence

from alr_tw.config import Settings
from alr_tw.contracts.provider_conformance import (
    ProviderConformanceRequest,
    ProviderConformanceStatus,
    validate_provider_conformance,
)
from alr_tw.contracts.provider_snapshot import ProviderSnapshotReceipt
from alr_tw.contracts.providers import ProviderResult
from alr_tw.contracts.sources import EvidenceSpan, SourceRecord
from alr_tw.providers.official import (
    OfficialConstitutionalProvider,
    OfficialJudgmentProvider,
    OfficialLawProvider,
)
from alr_tw.providers.official.http import safe_transport_error
from alr_tw.storage import PurgeService, SqliteStore


MAX_CONFORMANCE_ENVELOPE_BYTES = 4 * 1024 * 1024


def _storage_root(settings: Settings, override: str | None) -> Path:
    if override:
        return Path(override).expanduser()
    return settings.storage_path or Path.home() / ".cache" / "alr-tw"


def _read_conformance_envelope(path_value: str) -> dict:
    path = Path(path_value).expanduser()
    if not path.is_file():
        raise ValueError("PROVIDER_CONFORMANCE_INPUT_FILE_REQUIRED")
    if path.stat().st_size > MAX_CONFORMANCE_ENVELOPE_BYTES:
        raise ValueError("PROVIDER_CONFORMANCE_INPUT_TOO_LARGE")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("PROVIDER_CONFORMANCE_INPUT_INVALID")
    return payload


def _optional_json_array(payload: dict, key: str) -> list[Any]:
    value = payload.get(key, [])
    if not isinstance(value, list):
        raise ValueError(f"PROVIDER_CONFORMANCE_{key.upper()}_MUST_BE_ARRAY")
    return value


async def _doctor_live_checks() -> dict[str, Any]:
    """Probe the three official HTTPS providers without exposing secret values."""

    providers: list[Any] = [
        OfficialLawProvider(),
        OfficialConstitutionalProvider(),
        OfficialJudgmentProvider(),
    ]
    outcomes = await asyncio.gather(
        *(provider.health_check() for provider in providers),
        return_exceptions=True,
    )
    checks: list[dict[str, Any]] = []
    for provider, outcome in zip(providers, outcomes, strict=True):
        if isinstance(outcome, BaseException):
            message = safe_transport_error(
                outcome if isinstance(outcome, Exception) else RuntimeError(type(outcome).__name__)
            )
            checks.append(
                {
                    "provider_id": provider.provider_id,
                    "status": "unavailable",
                    "error_code": "OFFICIAL_SOURCE_UNAVAILABLE",
                    "message": message,
                }
            )
        else:
            checks.append(outcome.model_dump(mode="json"))
    return {
        "tls_backend": "system_truststore",
        "live_ready": all(item["status"] == "healthy" for item in checks),
        "provider_checks": checks,
    }


def _structural_cli_projection(decision: Any) -> dict[str, Any]:
    """Downgrade file-envelope results to caller-supplied structural diagnostics."""

    payload = decision.model_dump(mode="json")
    if payload.get("decision") == ProviderConformanceStatus.CONFORMING.value:
        payload["decision"] = ProviderConformanceStatus.QUALIFIED.value
    reasons = list(payload.get("reason_codes", []))
    marker = "PROVIDER_CLI_CALLER_SUPPLIED_ENVELOPE"
    if marker not in reasons:
        reasons.append(marker)
    payload.update(
        {
            "input_trust": "caller_supplied_envelope",
            "validation_scope": "structural_conformance_only",
            "runtime_promotion_authorized": False,
            "server_owned_decision": False,
            "ordinary_eligible": False,
            "absence_claim_allowed": False,
            "eligible_source_ids": [],
            "eligible_evidence_ids": [],
            "reason_codes": reasons,
        }
    )
    return payload


def _verify_provider(path_value: str) -> dict:
    payload = _read_conformance_envelope(path_value)
    allowed = {
        "request",
        "result",
        "server_sources",
        "server_evidence",
        "receipts",
        "server_receipts",
    }
    if unexpected := sorted(set(payload) - allowed):
        raise ValueError("PROVIDER_CONFORMANCE_INPUT_FIELDS_INVALID:" + ",".join(unexpected))
    request = ProviderConformanceRequest.model_validate(payload.get("request"))
    result = ProviderResult.model_validate(payload.get("result"))
    sources = [
        SourceRecord.model_validate(item)
        for item in _optional_json_array(payload, "server_sources")
    ]
    evidence = [
        EvidenceSpan.model_validate(item)
        for item in _optional_json_array(payload, "server_evidence")
    ]
    receipts = [
        ProviderSnapshotReceipt.model_validate(item)
        for item in _optional_json_array(payload, "receipts")
    ]
    server_receipts = [
        ProviderSnapshotReceipt.model_validate(item)
        for item in _optional_json_array(payload, "server_receipts")
    ]
    source_map = {item.source_id: item for item in sources}
    evidence_map = {item.evidence_id: item for item in evidence}
    if len(source_map) != len(sources) or len(evidence_map) != len(evidence):
        raise ValueError("PROVIDER_CONFORMANCE_SERVER_BINDING_DUPLICATE")
    decision = validate_provider_conformance(
        result,
        request=request,
        server_source_ids=list(source_map),
        server_evidence_ids=list(evidence_map),
        server_sources=source_map,
        server_evidence=evidence_map,
        receipts=receipts,
        server_receipts=server_receipts,
    )
    return _structural_cli_projection(decision)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="alr-tw")
    subcommands = parser.add_subparsers(dest="command", required=True)

    purge = subcommands.add_parser("purge", help="Delete managed research storage")
    target = purge.add_mutually_exclusive_group(required=True)
    target.add_argument("--run", dest="run_id", metavar="RUN_ID")
    target.add_argument("--all", action="store_true", dest="purge_all")
    purge.add_argument("--confirm", action="store_true", required=True)
    purge.add_argument("--storage-path")

    doctor = subcommands.add_parser("doctor", help="Validate redacted startup configuration")
    doctor.add_argument("--live", action="store_true", help="Require an explicit live data mode")
    doctor.add_argument("--storage-path")

    verify_provider = subcommands.add_parser(
        "verify-provider",
        help=(
            "Validate the structure of a caller-supplied provider conformance "
            "JSON envelope without authorizing runtime promotion"
        ),
    )
    verify_provider.add_argument(
        "--input",
        "--path",
        dest="input_path",
        required=True,
        help="Path to a provider conformance envelope JSON file",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    exit_code = 0
    try:
        if args.command == "purge":
            settings = Settings.from_env()
            store = SqliteStore(_storage_root(settings, args.storage_path))
            scope = "all" if args.purge_all else "run"
            result = PurgeService(store).purge(
                scope,
                run_id=args.run_id,
                confirmed=args.confirm,
            )
            payload = result.model_dump(mode="json")
        elif args.command == "doctor":
            settings = Settings.from_env()
            live_diagnostics: dict[str, Any] = {}
            if args.live:
                settings.require_live_mode()
                live_diagnostics = asyncio.run(_doctor_live_checks())
                if not live_diagnostics["live_ready"]:
                    exit_code = 1
            payload = {
                "ok": True,
                "data_mode": settings.data_mode.value,
                "storage_path": str(_storage_root(settings, args.storage_path)),
                "retention_seconds": settings.storage_policy.retention_seconds,
                "external_query_enabled": settings.external_query_enabled,
                "tlr_api_key_configured": settings.tlr_api_key is not None,
                "judicial_source": "public_website_html",
                **live_diagnostics,
            }
        else:
            payload = _verify_provider(args.input_path)
            if payload["decision"] == ProviderConformanceStatus.BLOCKED.value:
                exit_code = 1
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps({"ok": True, "data": payload}, ensure_ascii=False, sort_keys=True))
    return exit_code
