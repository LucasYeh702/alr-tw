"""Bounded HTTPS session for the Judicial Yuan judgment website."""

from __future__ import annotations

import importlib
from dataclasses import dataclass
from typing import Any, Mapping, Protocol
from urllib.parse import urljoin, urlparse


JUDICIAL_JUDGMENT_HOST = "judgment.judicial.gov.tw"


@dataclass(frozen=True)
class JudicialSiteResponse:
    status_code: int
    content: bytes
    headers: Mapping[str, str]
    url: str


class JudicialSiteTransport(Protocol):
    """Narrow transport used by the judgment provider and fixture tests."""

    async def open(self) -> None: ...

    async def close(self) -> None: ...

    async def get(
        self,
        url: str,
        *,
        timeout: float,
        max_bytes: int,
    ) -> JudicialSiteResponse: ...

    async def post_form(
        self,
        url: str,
        form: Mapping[str, str],
        *,
        timeout: float,
        max_bytes: int,
    ) -> JudicialSiteResponse: ...


class HttpxJudicialSiteTransport:
    """Cookie-preserving, fixed-host transport with redirect and byte limits."""

    def __init__(self, *, user_agent: str = "Mozilla/5.0 ALR-TW/0.6.2") -> None:
        self.user_agent = user_agent
        self._client: Any | None = None
        self._open_count = 0

    async def open(self) -> None:
        if self._client is None:
            httpx = self._httpx()
            self._client = httpx.AsyncClient(
                headers={"User-Agent": self.user_agent},
                follow_redirects=False,
            )
        self._open_count += 1

    async def close(self) -> None:
        if self._client is None:
            return
        self._open_count = max(0, self._open_count - 1)
        if self._open_count:
            return
        client, self._client = self._client, None
        await client.aclose()

    async def get(
        self,
        url: str,
        *,
        timeout: float,
        max_bytes: int,
    ) -> JudicialSiteResponse:
        return await self._request("GET", url, None, timeout=timeout, max_bytes=max_bytes)

    async def post_form(
        self,
        url: str,
        form: Mapping[str, str],
        *,
        timeout: float,
        max_bytes: int,
    ) -> JudicialSiteResponse:
        return await self._request("POST", url, form, timeout=timeout, max_bytes=max_bytes)

    @staticmethod
    def _validate_url(url: str) -> None:
        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.hostname != JUDICIAL_JUDGMENT_HOST:
            raise ValueError("URL_NOT_ALLOWLISTED")
        if parsed.username is not None or parsed.password is not None:
            raise ValueError("URL_CREDENTIALS_FORBIDDEN")

    async def _request(
        self,
        method: str,
        url: str,
        form: Mapping[str, str] | None,
        *,
        timeout: float,
        max_bytes: int,
    ) -> JudicialSiteResponse:
        httpx = self._httpx()
        current_url = url
        current_method = method
        current_form = dict(form) if form is not None else None
        client = self._client
        owns_client = client is None
        if client is None:
            client = httpx.AsyncClient(
                headers={"User-Agent": self.user_agent},
                follow_redirects=False,
            )
        try:
            for _ in range(4):
                self._validate_url(current_url)
                async with client.stream(
                    current_method,
                    current_url,
                    data=current_form if current_method == "POST" else None,
                    timeout=timeout,
                ) as response:
                    if response.status_code in {301, 302, 303, 307, 308}:
                        location = response.headers.get("location")
                        if not location:
                            raise RuntimeError("REDIRECT_WITHOUT_LOCATION")
                        current_url = urljoin(current_url, location)
                        if response.status_code == 303:
                            current_method = "GET"
                            current_form = None
                        continue
                    chunks: list[bytes] = []
                    size = 0
                    async for chunk in response.aiter_bytes():
                        size += len(chunk)
                        if size > max_bytes:
                            raise RuntimeError("RESPONSE_TOO_LARGE")
                        chunks.append(chunk)
                    return JudicialSiteResponse(
                        status_code=response.status_code,
                        content=b"".join(chunks),
                        headers=dict(response.headers),
                        url=str(response.url),
                    )
            raise RuntimeError("TOO_MANY_REDIRECTS")
        finally:
            if owns_client:
                await client.aclose()

    @staticmethod
    def _httpx() -> Any:
        try:
            return importlib.import_module("httpx")
        except ImportError as exc:  # pragma: no cover - base install smoke
            raise RuntimeError("LIVE_EXTRA_REQUIRED") from exc
