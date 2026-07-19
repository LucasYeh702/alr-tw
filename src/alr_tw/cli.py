"""ALR-TW operational CLI."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from alr_tw.config import Settings
from alr_tw.storage import PurgeService, SqliteStore


def _storage_root(settings: Settings, override: str | None) -> Path:
    if override:
        return Path(override).expanduser()
    return settings.storage_path or Path.home() / ".cache" / "alr-tw"


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
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        settings = Settings.from_env()
        if args.command == "purge":
            store = SqliteStore(_storage_root(settings, args.storage_path))
            scope = "all" if args.purge_all else "run"
            result = PurgeService(store).purge(
                scope,
                run_id=args.run_id,
                confirmed=args.confirm,
            )
            payload = result.model_dump(mode="json")
        else:
            if args.live:
                settings.require_live_mode()
            payload = {
                "ok": True,
                "data_mode": settings.data_mode.value,
                "storage_path": str(_storage_root(settings, args.storage_path)),
                "retention_seconds": settings.storage_policy.retention_seconds,
                "external_query_enabled": settings.external_query_enabled,
                "tlr_api_key_configured": settings.tlr_api_key is not None,
                "judicial_source": "public_website_html",
            }
    except (ValueError, OSError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps({"ok": True, "data": payload}, ensure_ascii=False, sort_keys=True))
    return 0
