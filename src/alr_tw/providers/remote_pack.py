"""Authenticated bounded exact-lookup transport; no candidate promotion fallback.

The response authenticates a complete pack plus a fresh request/run/snapshot
binding. HTTPS authenticates the configured peer; a separately managed MAC key
authenticates the publisher. This is an optional small-pack transport (8 MiB).
"""

from __future__ import annotations

from alr_tw.budget import charge_http_request

import asyncio
import importlib
import inspect
import base64
import hashlib
import hmac
import json
import secrets
import ssl
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Awaitable, Callable
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field

from alr_tw.contracts.providers import (
    ProviderCapabilities,
    ProviderHealth,
    ProviderHealthStatus,
    ProviderResult,
    ProviderResultStatus,
)
from alr_tw.providers.official.judgments import OfficialJudgmentProvider
from alr_tw.providers.data_pack import DataPackJudgmentProvider, bounded_read

MAX_IMAGE = 8 * 1024 * 1024
MAX_RESPONSE = 12 * 1024 * 1024


def canonical(value: dict[str, Any]) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()


def _key(path: Path) -> bytes:
    key = bounded_read(path, 4096)
    if len(key) < 32:
        raise ValueError("PACK_KEY_INVALID")
    return key


def _mac(key: bytes, value: dict[str, Any]) -> str:
    return hmac.new(key, canonical(value), hashlib.sha256).hexdigest()


class LookupRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: str = Field(pattern=r"^alr-tw.remote-pack-request/v1$")
    run_id: str = Field(pattern=r"^[A-Za-z0-9._:-]{1,128}$")
    nonce: str = Field(pattern=r"^[0-9a-f]{64}$")
    identifier: str = Field(min_length=1, max_length=200)
    snapshot_id: str = Field(pattern=r"^[A-Za-z0-9._-]{1,80}$")
    issued_at: datetime
    mac: str = Field(pattern=r"^[0-9a-f]{64}$")

    def unsigned(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude={"mac"})


def make_request(run_id: str, identifier: str, snapshot_id: str, key: bytes) -> LookupRequest:
    request = LookupRequest(
        schema_version="alr-tw.remote-pack-request/v1",
        run_id=run_id,
        identifier=identifier,
        snapshot_id=snapshot_id,
        nonce=secrets.token_hex(32),
        issued_at=datetime.now(UTC),
        mac="0" * 64,
    )
    return request.model_copy(update={"mac": _mac(key, request.unsigned())})


def serve_request(raw: bytes, root: Path, key_path: Path) -> bytes:
    """Pure publisher handler, usable behind an operator-controlled TLS endpoint."""
    if len(raw) > 4096:
        raise ValueError("PACK_REQUEST_INVALID")
    try:
        request = LookupRequest.model_validate_json(raw)
    except (ValueError, RecursionError) as exc:
        raise ValueError("PACK_REQUEST_INVALID") from exc
    key = _key(key_path)
    now = datetime.now(UTC)
    if request.issued_at.tzinfo is None or abs((now - request.issued_at).total_seconds()) > 60:
        raise ValueError("PACK_REQUEST_EXPIRED")
    if not hmac.compare_digest(request.mac, _mac(key, request.unsigned())):
        raise ValueError("PACK_REQUEST_AUTHENTICATION_FAILED")
    provider = DataPackJudgmentProvider(root / "pack.sqlite", root / "manifest.json", key_path)
    if provider.manifest.snapshot_id != request.snapshot_id:
        raise ValueError("PACK_SNAPSHOT_MISMATCH")
    image = bounded_read(root / "pack.sqlite", MAX_IMAGE)
    # A changed image after provider verification must not be served as trusted.
    if hashlib.sha256(image).hexdigest() != provider.manifest.sha256:
        raise ValueError("PACK_DIGEST_MISMATCH")
    body = {
        "schema_version": "alr-tw.remote-pack-response/v1",
        "request": request.unsigned(),
        "manifest": provider.manifest.model_dump(mode="json"),
        "image": base64.b64encode(image).decode(),
        "expires_at": (now + timedelta(seconds=60)).isoformat(),
    }
    return canonical({**body, "mac": _mac(key, body)})


class HttpsPackTransport:
    def __init__(self, endpoint: str):
        parsed = urlparse(endpoint)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.fragment
            or parsed.query
            or parsed.port not in {None, 443}
        ):
            raise ValueError("PACK_ENDPOINT_INVALID")
        self.endpoint = endpoint

    async def __call__(self, body: bytes) -> bytes:
        try:
            httpx: Any = importlib.import_module("httpx")
        except ImportError as exc:
            raise ValueError("PACK_HTTP_EXTRA_REQUIRED") from exc
        try:
            # One cancellable wall-clock budget includes DNS, TLS, headers and body.
            async with asyncio.timeout(20):
                async with httpx.AsyncClient(
                    verify=ssl.create_default_context(), follow_redirects=False,
                    timeout=20, trust_env=False,
                ) as client:
                    charge_http_request()
                    async with client.stream(
                        "POST", self.endpoint, content=body,
                        headers={"Content-Type": "application/json", "Accept-Encoding": "identity"},
                    ) as response:
                        if response.status_code in {301, 302, 303, 307, 308}:
                            raise ValueError("PACK_REDIRECT_FORBIDDEN")
                        if response.status_code != 200 or response.url != httpx.URL(self.endpoint):
                            raise ValueError("PACK_TRANSPORT_FAILED")
                        if response.headers.get("content-encoding", "identity").lower() != "identity":
                            raise ValueError("PACK_CONTENT_ENCODING_UNSUPPORTED")
                        chunks = []
                        size = 0
                        async for chunk in response.aiter_raw():
                            size += len(chunk)
                            if size > MAX_RESPONSE:
                                raise ValueError("PACK_RESPONSE_TOO_LARGE")
                            chunks.append(chunk)
                        return b"".join(chunks)
        except TimeoutError as exc:
            raise ValueError("PACK_TRANSPORT_TIMEOUT") from exc
        except (httpx.HTTPError, OSError) as exc:
            raise ValueError("PACK_TRANSPORT_FAILED") from exc


class RemotePackProvider:
    """An exact-only adapter with explicit same-run identity on every lookup."""

    provider_id = "attested_judgment_pack"

    def __init__(
        self,
        endpoint: str,
        snapshot_id: str,
        key_path: Path,
        *,
        transport: Callable[[bytes], bytes | Awaitable[bytes]] | None = None,
    ):
        # Validate the configured endpoint even when tests inject a transport.
        self.transport = transport or HttpsPackTransport(endpoint)
        HttpsPackTransport(endpoint)
        self.snapshot_id = snapshot_id
        self.key_path = key_path

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            exact_lookup=True,
            keyword_search=False,
            semantic_recall=False,
            official_verification=False,
            historical_versions=False,
            current_status_check=False,
            external_query_transfer=True,
        )

    async def health_check(self) -> ProviderHealth:
        try:
            _key(self.key_path)
        except ValueError:
            return ProviderHealth(
                provider_id=self.provider_id,
                status=ProviderHealthStatus.UNAVAILABLE,
                error_code="PACK_KEY_INVALID",
            )
        return ProviderHealth(provider_id=self.provider_id, status=ProviderHealthStatus.HEALTHY)

    async def search(self, query: str = "", *, limit: int = 10) -> ProviderResult:
        return ProviderResult(
            provider_id=self.provider_id,
            status=ProviderResultStatus.ERROR,
            coverage_complete=False,
            metadata={"error_code": "PACK_EXACT_ONLY"},
        )

    async def exact_lookup(
        self, identifier: str, *, run_id: str | None = None, now: datetime | None = None
    ):
        if not run_id:
            raise ValueError("PACK_RUN_REQUIRED")
        if OfficialJudgmentProvider.normalize_jid(identifier) != identifier:
            raise ValueError("PACK_IDENTITY_INVALID")
        key = _key(self.key_path)
        request = make_request(run_id, identifier, self.snapshot_id, key)
        pending = self.transport(request.model_dump_json().encode())
        raw = await pending if inspect.isawaitable(pending) else pending
        if len(raw) > MAX_RESPONSE:
            raise ValueError("PACK_RESPONSE_TOO_LARGE")
        try:
            body = json.loads(raw)
            if not isinstance(body, dict) or set(body) != {
                "schema_version",
                "request",
                "manifest",
                "image",
                "expires_at",
                "mac",
            }:
                raise ValueError("PACK_RESPONSE_INVALID")
            mac = body.pop("mac")
            if not isinstance(mac, str) or not hmac.compare_digest(mac, _mac(key, body)):
                raise ValueError("PACK_RESPONSE_AUTHENTICATION_FAILED")
            if (
                body["schema_version"] != "alr-tw.remote-pack-response/v1"
                or body["request"] != request.unsigned()
            ):
                raise ValueError("PACK_REQUEST_BINDING_MISMATCH")
            expiry = datetime.fromisoformat(body["expires_at"])
            timestamp = datetime.now(UTC)
            if expiry.tzinfo is None or not timestamp < expiry <= timestamp + timedelta(seconds=61):
                raise ValueError("PACK_RESPONSE_EXPIRED")
            image = base64.b64decode(body["image"], validate=True)
            if len(image) > MAX_IMAGE:
                raise ValueError("PACK_RESPONSE_TOO_LARGE")
            with tempfile.TemporaryDirectory(prefix="alr-pack-transport-") as temporary:
                root = Path(temporary)
                (root / "pack.sqlite").write_bytes(image)
                (root / "manifest.json").write_bytes(canonical(body["manifest"]))
                provider = DataPackJudgmentProvider(
                    root / "pack.sqlite", root / "manifest.json", self.key_path
                )
                if provider.manifest.snapshot_id != self.snapshot_id:
                    raise ValueError("PACK_SNAPSHOT_MISMATCH")
                if provider.manifest.provenance != "official_snapshot":
                    raise ValueError("PACK_SYNTHETIC_NOT_LIVE")
                # Local validation and source creation is deliberately shared.
                result, source, spans = await provider.exact_lookup(identifier, now=now)
                return result, source, spans
        except (TypeError, KeyError, ValueError, RecursionError) as exc:
            code = str(exc)
            if not code.startswith("PACK_") or len(code) > 80:
                code = "PACK_RESPONSE_INVALID"
            raise ValueError(code) from exc


def publisher_app(root: Path, key_path: Path):
    """WSGI application; deploy behind HTTPS, disable request/body access logs."""

    def application(environ, start_response):
        try:
            if environ.get("REQUEST_METHOD") != "POST":
                raise ValueError("PACK_REQUEST_INVALID")
            size = int(environ.get("CONTENT_LENGTH", "0"))
            if not 0 < size <= 4096:
                raise ValueError("PACK_REQUEST_INVALID")
            body = serve_request(environ["wsgi.input"].read(size), root, key_path)
            status = "200 OK"
        except (ValueError, OSError, KeyError):
            body = b'{"error":"PACK_REQUEST_REJECTED"}'
            status = "400 Bad Request"
        start_response(
            status, [("Content-Type", "application/json"), ("Content-Length", str(len(body)))]
        )
        return [body]

    return application
