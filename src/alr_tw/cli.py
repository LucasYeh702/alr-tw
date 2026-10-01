"""ALR-TW operational CLI."""

from __future__ import annotations

import argparse
import asyncio
import json
import re
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

    quick = subcommands.add_parser("quick-research", help="快速召回並回查至多五件裁判")
    quick.add_argument("--query", required=True)
    quick.add_argument("--max-judgments", type=int, choices=range(1, 6), default=5)
    quick.add_argument("--max-steps", type=int, choices=range(1, 33), default=12)
    quick.add_argument("--as-of-date")
    quick.add_argument("--storage-path")

    status = subcommands.add_parser("research-status", help="查看研究進度與待補資料")
    status.add_argument("--run", dest="run_id", required=True)
    status.add_argument("--storage-path")

    draft = subcommands.add_parser("validate-draft", help="以同次研究證據驗證草稿 JSON")
    draft.add_argument("--run", dest="run_id", required=True)
    draft.add_argument("--input", dest="input_path", required=True)
    draft.add_argument("--operation-id")
    draft.add_argument("--storage-path")

    for command in ("review-draft", "complete-research", "advise-draft"):
        workflow = subcommands.add_parser(command, help="檢視內部草稿或接續研究並嚴格驗證")
        workflow.add_argument("--run", dest="run_id", required=True)
        workflow.add_argument("--input", dest="input_path", required=True)
        workflow.add_argument("--storage-path")
        if command == "advise-draft":
            workflow.add_argument("--gateway-config", required=True)
        if command == "complete-research":
            workflow.add_argument("--operation-id", required=True)
            workflow.add_argument("--max-steps", type=int, choices=range(1, 33), default=12)

    pack = subcommands.add_parser("import-pack", help="驗證並匯入經認證的離線裁判資料包")
    pack.add_argument("input_path")
    pack.add_argument("--manifest", required=True)
    pack.add_argument("--key-file", required=True)
    pack.add_argument("--destination", required=True)

    builder = subcommands.add_parser("build-pack", help="由本機核對過的匯出資料建置資料包")
    builder.add_argument("input_path")
    builder.add_argument("--key-file", required=True)
    builder.add_argument("--destination", required=True)
    inspector = subcommands.add_parser("inspect-pack", help="驗證資料包並顯示品質摘要")
    inspector.add_argument("input_path")
    inspector.add_argument("--key-file", required=True)

    audit = subcommands.add_parser("audit-dataset", help="在評測端稽核固定 CSV，不修改原始資料")
    audit.add_argument("input_path")
    audit.add_argument("--revision", required=True)
    audit.add_argument("--sha256", required=True)
    audit.add_argument("--overlay")

    historical = subcommands.add_parser("lookup-historical-law", help="回查有限範圍官方歷史法條")
    historical.add_argument("--law-code", required=True)
    historical.add_argument("--article", required=True)
    historical.add_argument("--as-of", required=True)
    interpretation = subcommands.add_parser("lookup-interpretation", help="精確回查法務部函釋全文")
    interpretation.add_argument("--document-id", required=True)
    interpretation.add_argument("--number", required=True)
    quote = subcommands.add_parser("map-quote", help="將搜尋文字映回同次研究的權威原文")
    quote.add_argument("--run", dest="run_id", required=True)
    quote.add_argument("--source", required=True)
    quote.add_argument("--query", required=True)
    quote.add_argument("--storage-path")

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
        if args.command in {"quick-research", "research-status", "validate-draft", "review-draft", "complete-research", "advise-draft"}:
            from alr_tw.workflow_cli import run_workflow

            payload = run_workflow(args, Settings.from_env())
            if args.command in {"validate-draft", "complete-research"} and payload.get("safe_to_present") is not True:
                exit_code = 1
            if args.command == "review-draft" and payload.get("draft_text") is None:
                exit_code = 1
            if args.command == "advise-draft" and (
                payload.get("blockers") or payload.get("review", {}).get("decision") == "blocked"
            ):
                exit_code = 1
        elif args.command == "audit-dataset":
            from alr_tw.evaluation.dataset_audit import AuditDisposition, audit_csv
            from alr_tw.providers.data_pack import bounded_read
            dispositions = []
            if args.overlay:
                dispositions = [AuditDisposition.model_validate(item) for item in
                                json.loads(bounded_read(Path(args.overlay), 1000000))]
            payload = audit_csv(bounded_read(Path(args.input_path), 20000000),
                                revision=args.revision, expected_sha256=args.sha256,
                                law_aliases={"中華民國刑法": "刑法", "刑法": "刑法", "民法": "民法",
                                             "刑事訴訟法": "刑事訴訟法", "民事訴訟法": "民事訴訟法",
                                             "行政訴訟法": "行政訴訟法", "行政程序法": "行政程序法"},
                                dispositions=dispositions)
        elif args.command in {"lookup-historical-law", "lookup-interpretation"}:
            from datetime import date
            from alr_tw.contracts.historical_law import HistoricalLawQuery
            from alr_tw.providers.official.bounded_law import (
                OfficialHistoricalLawProvider, OfficialInterpretationProvider,
            )
            if args.command == "lookup-historical-law":
                query = HistoricalLawQuery(query_id="cli-historical", law_identifier=args.law_code,
                                           as_of_date=date.fromisoformat(args.as_of),
                                           bounded_scope="one-official-historical-article")
                historical_result = asyncio.run(OfficialHistoricalLawProvider().lookup(query, args.article))
                source_result = historical_result.model_dump(mode="json")
            else:
                interpretation_result = asyncio.run(OfficialInterpretationProvider().lookup(args.document_id, args.number))
                source_result = interpretation_result.model_dump(mode="json")
            payload = {"result": source_result, "final_answer_authorized": False}
        elif args.command == "map-quote":
            from alr_tw.research.quote_workspace import map_source_quote
            settings = Settings.from_env()
            payload = map_source_quote(SqliteStore(_storage_root(settings, args.storage_path)),
                                       args.run_id, args.source, args.query)
        elif args.command in {"build-pack", "inspect-pack"}:
            from alr_tw.providers.pack_builder import build_pack, inspect_pack

            if args.command == "build-pack":
                payload = build_pack(Path(args.input_path), Path(args.key_file), Path(args.destination))
            else:
                payload = inspect_pack(Path(args.input_path), Path(args.key_file))
        elif args.command == "import-pack":
            from alr_tw.providers.data_pack import import_pack

            payload = import_pack(Path(args.input_path), Path(args.manifest),
                                  Path(args.key_file), Path(args.destination))
        elif args.command == "purge":
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
            pack_diagnostics: dict[str, Any] = {"configured": (settings.data_pack_root is not None or settings.remote_pack_endpoint is not None)}
            if settings.data_pack_root is not None or settings.remote_pack_endpoint:
                from alr_tw.providers.data_pack import configured_pack_provider

                pack_provider = configured_pack_provider(settings)
                pack_diagnostics.update(
                    health=asyncio.run(pack_provider.health_check()).status.value,
                    snapshot_id=(settings.remote_pack_snapshot if settings.remote_pack_endpoint
                                 else pack_provider.manifest.snapshot_id),
                    active=settings.data_mode.value != "synthetic",
                    coverage_complete=False,
                    external_query_transfer=bool(settings.remote_pack_endpoint),
                    network_checked=False,
                )
            payload = {
                "ok": True,
                "data_pack": pack_diagnostics,
                "data_mode": settings.data_mode.value,
                "storage_configured": True,
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
        error = str(exc)
        if args.command in {
            "audit-dataset", "map-quote", "lookup-historical-law", "lookup-interpretation",
            "build-pack", "inspect-pack", "import-pack", "doctor",
        } and not re.fullmatch(r"[A-Z][A-Z0-9_]{2,100}", error):
            error = ("CONFIG_MODE_REQUIRED" if error.startswith("CONFIG_MODE_REQUIRED:")
                     else "REQUEST_FAILED")
        failure: dict[str, Any] = {"ok": False, "error": error}
        if args.command in {"quick-research", "research-status", "validate-draft", "review-draft", "complete-research", "advise-draft"}:
            from alr_tw.research.workflow_guidance import build_error_guidance

            failure["workflow_guidance"] = build_error_guidance(str(exc))
        print(json.dumps(failure, ensure_ascii=False))
        return 2
    print(json.dumps({"ok": True, "data": payload}, ensure_ascii=False, sort_keys=True))
    return exit_code
