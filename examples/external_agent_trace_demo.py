from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from tw_legal_rag_mcp.verification.identifier_resolver import (
    SYNTHETIC_OFFICIAL_RECORDS,
    compute_content_hash,
)
from tw_legal_rag_mcp.verification.source_policy import (
    IDENTIFIER_BACKED_VERIFIED_CACHE_ENV,
)

ROOT = Path(__file__).resolve().parents[1]
DEMO_JID = "DEMO,113,測,1,20990101,1"
DEMO_HASH = compute_content_hash(SYNTHETIC_OFFICIAL_RECORDS[DEMO_JID])


def _server_env() -> dict[str, str]:
    env = dict(os.environ)
    env[IDENTIFIER_BACKED_VERIFIED_CACHE_ENV] = "1"
    src_path = str(ROOT / "src")
    env["PYTHONPATH"] = (
        src_path if not env.get("PYTHONPATH") else src_path + os.pathsep + env["PYTHONPATH"]
    )
    return env


def _send(proc: subprocess.Popen[str], request: dict[str, Any]) -> dict[str, Any]:
    assert proc.stdin is not None
    assert proc.stdout is not None
    proc.stdin.write(json.dumps(request, ensure_ascii=False, separators=(",", ":")) + "\n")
    proc.stdin.flush()
    line = proc.stdout.readline()
    if not line:
        stderr = proc.stderr.read() if proc.stderr is not None else ""
        raise RuntimeError(f"MCP server closed stdout unexpectedly: {stderr}")
    response = json.loads(line)
    if "error" in response:
        raise RuntimeError(json.dumps(response["error"], ensure_ascii=False))
    return response


def _notify_initialized(proc: subprocess.Popen[str]) -> None:
    assert proc.stdin is not None
    proc.stdin.write(
        json.dumps(
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            ensure_ascii=False,
            separators=(",", ":"),
        )
        + "\n"
    )
    proc.stdin.flush()


def _call_tool(
    proc: subprocess.Popen[str],
    request_id: int,
    name: str,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    response = _send(
        proc,
        {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        },
    )
    envelope = json.loads(response["result"]["content"][0]["text"])
    if not envelope["ok"]:
        raise RuntimeError(json.dumps(envelope["error"], ensure_ascii=False))
    return envelope["data"]


def _initialize(proc: subprocess.Popen[str]) -> None:
    _send(
        proc,
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "external-agent-trace-demo", "version": "0.5.0"},
            },
        },
    )
    _notify_initialized(proc)


def _passing_run(proc: subprocess.Popen[str]) -> dict[str, Any]:
    answer = "法院認為押金可否返還需依契約約定與事實情節判斷。"
    run_id = _call_tool(
        proc,
        2,
        "begin_agentic_run",
        {"query": "民法第184條 押金"},
    )["run_id"]
    _call_tool(proc, 3, "legal_search", {"query": "民法第184條 押金"})
    _call_tool(
        proc,
        4,
        "validate_citation",
        {
            "citation_id": "verified-demo-judgment",
            "source_tier": "verified_cache",
            "official_identifier": DEMO_JID,
            "official_hash": DEMO_HASH,
            "verified_at": "2099-01-01T00:00:00Z",
            "source_label": "Synthetic identifier-backed judgment",
            "legal_material_type": "judgment",
        },
    )
    claims = _call_tool(proc, 5, "extract_answer_claims", {"answer": answer})["claims"]
    claims[0]["referenced_citation_ids"] = ["verified-demo-judgment"]
    _call_tool(
        proc,
        6,
        "check_claim_support",
        {
            "answer": answer,
            "claims": claims,
            "segments": [
                {
                    "segment_id": "verified-demo-judgment-seg-01",
                    "source_id": "verified-demo-judgment",
                    "citation_id": "verified-demo-judgment",
                    "source_tier": "verified_cache",
                    "legal_material_type": "judgment",
                    "section_role": "court_reasoning",
                    "span_start": 0,
                    "span_end": 36,
                    "text": answer,
                    "official_identifier": DEMO_JID,
                    "content_hash": DEMO_HASH,
                    "verified_at": "2099-01-01T00:00:00Z",
                }
            ],
        },
    )
    return _call_tool(proc, 7, "finalize_agentic_run", {"run_id": run_id, "answer": answer})


def _refused_run(proc: subprocess.Popen[str]) -> dict[str, Any]:
    run_id = _call_tool(
        proc,
        8,
        "begin_agentic_run",
        {"query": "民法第184條 押金"},
    )["run_id"]
    _call_tool(proc, 9, "legal_search", {"query": "民法第184條 押金"})
    _call_tool(
        proc,
        10,
        "validate_citation",
        {
            "citation_id": "tlr-candidate-demo-001",
            "source_tier": "external_semantic_recall",
            "source_label": "Synthetic TLR Candidate",
            "legal_material_type": "judgment",
        },
    )
    return _call_tool(
        proc,
        11,
        "finalize_agentic_run",
        {"run_id": run_id, "answer": "Candidate-only answer must be dropped."},
    )


def main() -> int:
    proc = subprocess.Popen(
        [sys.executable, "-m", "tw_legal_rag_mcp.mcp_server"],
        cwd=ROOT,
        env=_server_env(),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        _initialize(proc)
        passing = _passing_run(proc)
        refused = _refused_run(proc)
    finally:
        proc.terminate()
        proc.communicate(timeout=5)

    print("PASSING RUN")
    print(json.dumps(passing, ensure_ascii=False, indent=2))
    print()
    print("REFUSED RUN")
    print(json.dumps(refused, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
