"""Small allowlisted HTTP transport for official providers."""

from __future__ import annotations

import importlib
from dataclasses import dataclass
from typing import Any, Mapping, Protocol
from urllib.parse import urljoin, urlparse


@dataclass(frozen=True)
class HttpResponse:
    status_code: int
    content: bytes
    headers: Mapping[str, str]
    url: str


class HttpTransport(Protocol):
    async def get(self, url: str, *, timeout: float, max_bytes: int) -> HttpResponse: ...


class HttpxAllowlistedTransport:
    """HTTPS-only transport with redirect and response-size validation."""

    def __init__(self, allowed_hosts: set[str], *, user_agent: str = "ALR-TW/0.6.1"):
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
