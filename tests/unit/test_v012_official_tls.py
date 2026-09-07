from __future__ import annotations

import asyncio
import ssl
from typing import Any

from alr_tw.providers.official import http as official_http
from alr_tw.providers.official import judicial_site


class _Response:
    status_code = 200
    headers: dict[str, str] = {}
    url = "https://law.moj.gov.tw/example"

    async def __aenter__(self) -> _Response:
        return self

    async def __aexit__(self, *args: object) -> None:
        del args

    async def aiter_bytes(self):
        yield b"ok"


class _Client:
    created_with: list[dict[str, Any]] = []

    def __init__(self, **kwargs: Any) -> None:
        self.created_with.append(kwargs)

    async def __aenter__(self) -> _Client:
        return self

    async def __aexit__(self, *args: object) -> None:
        del args

    def stream(self, *args: object, **kwargs: object) -> _Response:
        del args, kwargs
        return _Response()

    async def aclose(self) -> None:
        return None


class _HttpxModule:
    AsyncClient = _Client


class _TruststoreModule:
    context = object()

    @classmethod
    def SSLContext(cls, protocol: object) -> object:
        del protocol
        return cls.context


def test_official_allowlisted_http_uses_system_truststore(monkeypatch) -> None:
    def fake_import(name: str) -> object:
        return _HttpxModule if name == "httpx" else _TruststoreModule

    _Client.created_with.clear()
    monkeypatch.setattr(official_http.importlib, "import_module", fake_import)
    transport = official_http.HttpxAllowlistedTransport({"law.moj.gov.tw"})

    asyncio.run(
        transport.get(
            "https://law.moj.gov.tw/example",
            timeout=1,
            max_bytes=100,
        )
    )

    assert _Client.created_with[0]["verify"] is _TruststoreModule.context


def test_judicial_site_http_uses_system_truststore(monkeypatch) -> None:
    _Client.created_with.clear()
    monkeypatch.setattr(
        judicial_site.importlib,
        "import_module",
        lambda name: _HttpxModule,
    )
    monkeypatch.setattr(
        judicial_site,
        "system_truststore_context",
        lambda: _TruststoreModule.context,
    )
    transport = judicial_site.HttpxJudicialSiteTransport()

    asyncio.run(
        transport.get(
            "https://judgment.judicial.gov.tw/FJUD/Default_AD.aspx",
            timeout=1,
            max_bytes=100,
        )
    )

    assert _Client.created_with[0]["verify"] is _TruststoreModule.context


def test_official_tls_failure_is_classified_without_raw_exception_text() -> None:
    exc = RuntimeError("[SSL: CERTIFICATE_VERIFY_FAILED] private-path")

    assert official_http.safe_transport_error(exc) == "OFFICIAL_TLS_VERIFICATION_FAILED"


def test_non_tls_failure_containing_ssl_text_keeps_original_error_class() -> None:
    class ConnectTimeout(Exception):
        pass

    exc = ConnectTimeout("connection to https://example.org/ssl/query timed out")
    assert official_http.safe_transport_error(exc) == "ConnectTimeout"


def test_wrapped_certificate_exception_is_classified_by_type() -> None:
    exc = RuntimeError("transport failure")
    exc.__cause__ = ssl.SSLCertVerificationError("synthetic certificate failure")
    assert official_http.safe_transport_error(exc) == "OFFICIAL_TLS_VERIFICATION_FAILED"


def test_tlr_http_uses_system_truststore(monkeypatch) -> None:
    from alr_tw.providers.tlr.provider import HttpxTlrTransport
    from alr_tw.providers.tlr import provider as tlr_provider

    class _TlrResponse:
        status_code = 200
        headers: dict[str, str] = {}

        async def __aenter__(self) -> _TlrResponse:
            return self

        async def __aexit__(self, *args: object) -> None:
            del args

        async def aiter_bytes(self):
            yield b"{}"

    class _TlrClient:
        created_with: list[dict[str, Any]] = []

        def __init__(self, **kwargs: Any) -> None:
            self.created_with.append(kwargs)

        async def __aenter__(self) -> _TlrClient:
            return self

        async def __aexit__(self, *args: object) -> None:
            del args

        def stream(self, *args: object, **kwargs: object) -> _TlrResponse:
            del args, kwargs
            return _TlrResponse()

    class _TlrHttpxModule:
        AsyncClient = _TlrClient

    _TlrClient.created_with.clear()
    monkeypatch.setattr(
        tlr_provider.importlib,
        "import_module",
        lambda name: _TlrHttpxModule,
    )
    monkeypatch.setattr(
        tlr_provider,
        "system_truststore_context",
        lambda: _TruststoreModule.context,
    )

    asyncio.run(
        HttpxTlrTransport()._request(
            "GET",
            "https://tlr.dr-lawbot.com/v1/search",
            None,
            {},
            1,
            100,
        )
    )

    assert _TlrClient.created_with[0]["verify"] is _TruststoreModule.context
