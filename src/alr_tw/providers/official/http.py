"""Small allowlisted HTTP transport for official providers."""

from __future__ import annotations

import importlib
import ssl
from dataclasses import dataclass
from typing import Any, Mapping, Protocol
from urllib.parse import urljoin, urlparse

from alr_tw._version import __version__


@dataclass(frozen=True)
class HttpResponse:
    status_code: int
    content: bytes
    headers: Mapping[str, str]
    url: str


class HttpTransport(Protocol):
    async def get(self, url: str, *, timeout: float, max_bytes: int) -> HttpResponse: ...


def system_truststore_context() -> ssl.SSLContext:
    """Build an SSL context backed by the operating system trust store."""

    try:
        truststore: Any = importlib.import_module("truststore")
    except ImportError as exc:  # pragma: no cover - exercised by base-install smoke
        raise RuntimeError("LIVE_TRUSTSTORE_REQUIRED") from exc
    return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)


def safe_transport_error(exc: Exception) -> str:
    """Return a stable, non-secret diagnostic for an official HTTPS failure."""

    messages: list[str] = []
    current: BaseException | None = exc
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if isinstance(current, ssl.SSLCertVerificationError):
            return "OFFICIAL_TLS_VERIFICATION_FAILED"
        messages.append(str(current))
        current = current.__cause__ or current.__context__
    joined = " ".join(messages).upper()
    if "LIVE_TRUSTSTORE_REQUIRED" in joined:
        return "LIVE_TRUSTSTORE_REQUIRED"
    if "LIVE_EXTRA_REQUIRED" in joined:
        return "LIVE_EXTRA_REQUIRED"
    if "CERTIFICATE_VERIFY_FAILED" in joined:
        return "OFFICIAL_TLS_VERIFICATION_FAILED"
    return type(exc).__name__


class HttpxAllowlistedTransport:
    """HTTPS-only transport with redirect and response-size validation."""

    def __init__(
        self,
        allowed_hosts: set[str],
        *,
        user_agent: str = f"ALR-TW/{__version__}",
    ):
        self.allowed_hosts = {host.lower() for host in allowed_hosts}
        self.user_agent = user_agent

    def validate_url(self, url: str) -> None:
        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.hostname not in self.allowed_hosts:
            raise ValueError("URL_NOT_ALLOWLISTED")
        if parsed.username or parsed.password:
            raise ValueError("URL_CREDENTIALS_FORBIDDEN")

    async def get(self, url: str, *, timeout: float, max_bytes: int) -> HttpResponse:
        try:
            httpx: Any = importlib.import_module("httpx")
        except ImportError as exc:  # pragma: no cover - exercised by base-install smoke
            raise RuntimeError("LIVE_EXTRA_REQUIRED") from exc

        current = url
        async with httpx.AsyncClient(
            headers={"User-Agent": self.user_agent},
            follow_redirects=False,
            timeout=timeout,
            verify=system_truststore_context(),
        ) as client:
            for _ in range(4):
                self.validate_url(current)
                async with client.stream("GET", current) as response:
                    if response.status_code in {301, 302, 303, 307, 308}:
                        location = response.headers.get("location")
                        if not location:
                            raise RuntimeError("REDIRECT_WITHOUT_LOCATION")
                        current = urljoin(current, location)
                        continue
                    chunks: list[bytes] = []
                    size = 0
                    async for chunk in response.aiter_bytes():
                        size += len(chunk)
                        if size > max_bytes:
                            raise RuntimeError("RESPONSE_TOO_LARGE")
                        chunks.append(chunk)
                    return HttpResponse(
                        status_code=response.status_code,
                        content=b"".join(chunks),
                        headers=dict(response.headers),
                        url=str(response.url),
                    )
        raise RuntimeError("TOO_MANY_REDIRECTS")
