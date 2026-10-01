"""Real loopback TLS, without public DNS or external network access."""

import asyncio
import ssl
import subprocess
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

import pytest

from alr_tw.providers.remote_pack import HttpsPackTransport


@pytest.fixture
def tls_endpoint(tmp_path, monkeypatch):
    cert, key = tmp_path / "cert.pem", tmp_path / "key.pem"
    config = tmp_path / "openssl.cnf"
    config.write_text(
        "[req]\ndistinguished_name=dn\nx509_extensions=ext\nprompt=no\n"
        "[dn]\nCN=localhost\n[ext]\nsubjectAltName=DNS:localhost\n"
    )
    subprocess.run(
        ["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1",
         "-config", str(config), "-keyout", str(key), "-out", str(cert)],
        capture_output=True, check=True, timeout=20,
    )
    received = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            received.append(self.rfile.read(int(self.headers["Content-Length"])))
            if self.path == "/redirect":
                self.send_response(302)
                self.send_header("Location", "/exact")
            else:
                self.send_response(200)
            self.send_header("Content-Length", "2")
            self.end_headers()
            self.wfile.write(b"{}")

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(cert, key)
    server.socket = context.wrap_socket(server.socket, server_side=True)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setenv("no_proxy", "localhost,127.0.0.1")
    try:
        yield f"https://localhost:{server.server_port}", cert, received
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def transport_for_loopback(url):
    transport = HttpsPackTransport("https://localhost/exact")
    # Production only permits 443; tests use an unprivileged ephemeral port.
    transport.endpoint = url
    return transport


def test_tls_rejects_untrusted_peer_before_request(tls_endpoint):
    url, _, received = tls_endpoint
    with pytest.raises(ValueError, match="PACK_TRANSPORT_FAILED"):
        asyncio.run(transport_for_loopback(url + "/exact")(b"synthetic"))
    assert received == []


def test_tls_validates_peer_and_forbids_redirect(tls_endpoint, monkeypatch):
    url, cert, received = tls_endpoint
    context = ssl.create_default_context(cafile=str(cert))
    monkeypatch.setattr(ssl, "create_default_context", lambda: context)
    assert asyncio.run(transport_for_loopback(url + "/exact")(b"synthetic")) == b"{}"
    with pytest.raises(ValueError, match="PACK_REDIRECT_FORBIDDEN"):
        asyncio.run(transport_for_loopback(url + "/redirect")(b"synthetic"))
    assert len(received) == 2
