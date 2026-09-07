"""在隔離直譯器驗證 wheel；只使用合成回應，不呼叫外部法律服務。"""
from __future__ import annotations

import argparse
import asyncio
import importlib.metadata
import importlib.util
import json
import os
from pathlib import Path
import ssl
import subprocess
import sys
import tempfile
from unittest.mock import patch


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", choices=["base", "tlr"], required=True)
    parser.add_argument("--version", required=True)
    args = parser.parse_args()
    import alr_tw
    import tw_legal_rag_mcp

    assert importlib.metadata.version("alr-tw") == alr_tw.__version__ == args.version
    prefix = Path(sys.prefix).resolve()
    for module in (alr_tw, tw_legal_rag_mcp):
        assert Path(module.__file__).resolve().is_relative_to(prefix)
    if args.profile == "base":
        assert importlib.util.find_spec("httpx") is None
        assert importlib.util.find_spec("truststore") is None
    else:
        import httpx
        from alr_tw.providers.official.http import system_truststore_context
        from alr_tw.providers.tlr.provider import HttpxTlrTransport

        assert importlib.util.find_spec("bs4") is None
        assert importlib.util.find_spec("lxml") is None
        context = system_truststore_context()
        assert context.verify_mode == ssl.CERT_REQUIRED and context.check_hostname
        actual_client = httpx.AsyncClient

        def mock_client(**kwargs):
            assert kwargs["verify"].verify_mode == ssl.CERT_REQUIRED
            kwargs["transport"] = httpx.MockTransport(
                lambda request: httpx.Response(200, json={"synthetic": True})
            )
            return actual_client(**kwargs)

        with patch("httpx.AsyncClient", mock_client):
            response = asyncio.run(HttpxTlrTransport().get_json(
                "https://example.test/health",
                headers={}, timeout=1.0, max_bytes=1024,
            ))
        assert response.status_code == 200 and response.payload == {"synthetic": True}

    # 不繼承本機設定；不將 doctor 可能包含路徑的 JSON 寫入測試日誌。
    env = {key: value for key, value in os.environ.items()
           if not key.startswith(("ALR_TW_", "TLR_"))
           and key not in {"PYTHONPATH", "PYTHONHOME"}}
    env["ALR_TW_DATA_MODE"] = "synthetic"
    env["ALR_TW_MCP_TOOL_PROFILE"] = "verified"
    with tempfile.TemporaryDirectory() as directory:
        env["ALR_TW_STORAGE_PATH"] = str(Path(directory) / "state")
        doctor = subprocess.run(
            [sys.executable, "-I", "-c",
             "from alr_tw.cli import main; raise SystemExit(main(['doctor']))"],
            cwd=directory, env=env, capture_output=True, text=True, timeout=30,
        )
        assert doctor.returncode == 0
        assert json.loads(doctor.stdout)["ok"] is True
        requests = [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
                "protocolVersion": "2025-11-25", "capabilities": {},
                "clientInfo": {"name": "synthetic-install-smoke", "version": "1"},
            }},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        ]
        result = subprocess.run(
            [sys.executable, "-I", "-m", "tw_legal_rag_mcp.mcp_server"],
            input="".join(json.dumps(item) + "\n" for item in requests),
            cwd=directory, env=env, capture_output=True, text=True, timeout=30,
        )
        assert result.returncode == 0
        replies = {item["id"]: item for item in
                   (json.loads(line) for line in result.stdout.splitlines() if line.strip())}
        assert replies[1]["result"]["serverInfo"]["version"] == args.version
        assert any(tool["name"] == "execute_legal_research"
                   for tool in replies[2]["result"]["tools"])
    print("PASS: installed package, isolated imports, doctor, MCP stdio; profile=" + args.profile)


if __name__ == "__main__":
    main()
