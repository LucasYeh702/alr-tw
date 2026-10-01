import asyncio
from types import SimpleNamespace

import httpx
import pytest

from alr_tw.providers import remote_pack
from alr_tw.providers.official import http


@pytest.mark.parametrize("kind", ["remote", "official"])
def test_continuous_small_chunks_cannot_extend_total_deadline(monkeypatch, kind):
    closed = []

    class SlowBody(httpx.AsyncByteStream):
        async def __aiter__(self):
            while True:
                await asyncio.sleep(0.005)
                yield b"x"

        async def aclose(self):
            closed.append(True)

    async def respond(request):
        return httpx.Response(200, stream=SlowBody())

    original = httpx.AsyncClient
    monkeypatch.setattr(
        httpx, "AsyncClient",
        lambda **kwargs: original(**{**kwargs, "transport": httpx.MockTransport(respond)}),
    )
    if kind == "remote":
        monkeypatch.setattr(remote_pack, "asyncio", SimpleNamespace(
            timeout=lambda _: asyncio.timeout(0.05)
        ))
        with pytest.raises(ValueError, match="PACK_TRANSPORT_TIMEOUT"):
            asyncio.run(remote_pack.HttpsPackTransport("https://example.test/")(b"{}"))
    else:
        with pytest.raises(TimeoutError):
            asyncio.run(http.HttpxAllowlistedTransport({"example.test"}).get(
                "https://example.test/", timeout=0.05, max_bytes=100000,
            ))
    assert closed == [True]


@pytest.mark.parametrize("encoding", [None, "gzip"])
def test_remote_normalizes_default_port_and_requests_identity_encoding(monkeypatch, encoding):
    async def respond(request):
        assert request.headers["accept-encoding"] == "identity"
        return httpx.Response(200, stream=httpx.ByteStream(b"{}"), headers=(
            {"Content-Encoding": encoding} if encoding else {}
        ))

    original = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: original(
        **{**kwargs, "transport": httpx.MockTransport(respond)}
    ))
    request = remote_pack.HttpsPackTransport("https://example.test:443/exact")(b"{}")
    if encoding:
        with pytest.raises(ValueError, match="PACK_CONTENT_ENCODING_UNSUPPORTED"):
            asyncio.run(request)
    else:
        assert asyncio.run(request) == b"{}"
