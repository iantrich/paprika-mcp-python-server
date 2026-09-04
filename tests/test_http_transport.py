"""Transport-level tests for the streamable HTTP app."""
import json
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from starlette.testclient import TestClient

from paprika_mcp_server.transports.http import build_app

INIT = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2025-06-18",
        "capabilities": {},
        "clientInfo": {"name": "test", "version": "0"},
    },
}
TOOLS_LIST = {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}
HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json, text/event-stream",
}


@pytest.fixture
def app():
    return build_app(MagicMock(), None)


def _payload(response):
    """Parse a streamable-HTTP response body, JSON or SSE-framed."""
    body = response.text
    if response.headers.get("content-type", "").startswith("text/event-stream"):
        for line in body.splitlines():
            if line.startswith("data:"):
                return json.loads(line[len("data:"):].strip())
        raise AssertionError(f"no SSE data frame in response: {body!r}")
    return json.loads(body)


def test_healthz_is_ok(app):
    with TestClient(app) as c:
        r = c.get("/healthz")
        assert r.status_code == 200


def test_mcp_endpoint_accepts_initialize(app):
    with TestClient(app) as c:
        r = c.post("/mcp", json=INIT, headers=HEADERS)
        assert r.status_code == 200


@pytest.mark.parametrize("path", ["/mcp", "/mcp/"])
def test_mcp_path_is_not_a_redirect(app, path):
    """Neither spelling may redirect: a 307 drops the body and Authorization
    header. A Mount would 307 "/mcp" -> "/mcp/"; a single Route with
    redirect_slashes (the Starlette default) would 307 "/mcp/" -> "/mcp"."""
    with TestClient(app, follow_redirects=False) as c:
        r = c.post(path, json=INIT, headers=HEADERS)
        assert r.status_code != 307, f"POST {path} is redirecting"


@pytest.mark.parametrize("path", ["/mcp", "/mcp/"])
def test_tools_list_over_http_returns_all_17_tools(app, path):
    """End-to-end through ASGI + session manager + MCP protocol layer.

    Exercises the real request path without Paprika credentials: the client is
    a MagicMock, and tools/list never touches it. Parametrized over both path
    spellings so "/mcp/" is proven to actually reach the session manager, not
    just to avoid a 307.
    """
    from paprika_mcp_server.core.tools import TOOLS

    with TestClient(app) as c:
        r = c.post(path, json=TOOLS_LIST, headers=HEADERS)
        assert r.status_code == 200, r.text
        data = _payload(r)
        assert "error" not in data, data
        names = [t["name"] for t in data["result"]["tools"]]

    assert len(names) == 17, names
    assert sorted(names) == sorted(t.name for t in TOOLS)


def test_stateless_mode_needs_no_session_id(app):
    """Stateless: a second, unrelated POST works with no mcp-session-id."""
    with TestClient(app) as c:
        first = c.post("/mcp", json=TOOLS_LIST, headers=HEADERS)
        second = c.post("/mcp", json=TOOLS_LIST, headers=HEADERS)
    assert first.status_code == 200
    assert second.status_code == 200, second.text
    assert "error" not in _payload(second)


def test_unknown_path_is_404(app):
    with TestClient(app) as c:
        assert c.get("/nope").status_code == 404


class TestOriginValidation:
    """DNS-rebinding defence. See OriginValidationMiddleware.

    Host is deliberately NOT validated: cloudflared forwards
    Host: <random>.trycloudflare.com, and a host allowlist would reject the
    tunnel with a confusing 421.
    """

    def test_foreign_origin_is_rejected(self, app):
        """A browser page on an attacker's domain must not reach the tools."""
        with TestClient(app) as c:
            r = c.post(
                "/mcp",
                json=TOOLS_LIST,
                headers={**HEADERS, "Origin": "https://evil.example.com"},
            )
        assert r.status_code == 403, r.text

    def test_request_with_no_origin_succeeds(self, app):
        """Server-to-server is how Claude reaches this, tunnel or not.

        Non-browser clients send no Origin header; blocking them would break
        the whole transport.
        """
        with TestClient(app) as c:
            r = c.post("/mcp", json=TOOLS_LIST, headers=HEADERS)
        assert r.status_code == 200, r.text
        assert "error" not in _payload(r)

    @pytest.mark.parametrize(
        "origin",
        ["http://localhost:6274", "http://127.0.0.1:8080", "http://[::1]:8080"],
    )
    def test_loopback_origins_are_allowed(self, origin):
        """A same-machine browser tool (MCP Inspector) keeps working."""
        with TestClient(build_app(MagicMock(), None)) as c:
            r = c.post("/mcp", json=TOOLS_LIST, headers={**HEADERS, "Origin": origin})
        assert r.status_code == 200, r.text

    def test_explicitly_allowed_origin_is_accepted(self):
        """--allowed-origin extends the allowlist beyond loopback."""
        app = build_app(MagicMock(), None, allowed_origins=["https://app.example.com"])
        with TestClient(app) as c:
            r = c.post(
                "/mcp",
                json=TOOLS_LIST,
                headers={**HEADERS, "Origin": "https://app.example.com"},
            )
        assert r.status_code == 200, r.text

    def test_foreign_origin_is_rejected_on_healthz_too(self, app):
        with TestClient(app) as c:
            r = c.get("/healthz", headers={"Origin": "https://evil.example.com"})
        assert r.status_code == 403


def test_cli_allowed_origin_flag_is_repeatable_and_forwarded():
    """`serve-http --allowed-origin A --allowed-origin B` reaches run_http."""
    from paprika_mcp_server import cli

    seen = {}

    def _fake_run_http(host, port, allowed_origins):
        seen.update(host=host, port=port, allowed_origins=allowed_origins)

    argv = [
        "paprika-mcp", "serve-http",
        "--allowed-origin", "https://a.example.com",
        "--allowed-origin", "https://b.example.com",
    ]
    with patch.object(sys, "argv", argv), \
         patch("paprika_mcp_server.transports.http.run_http", _fake_run_http):
        cli.main()

    assert seen["allowed_origins"] == [
        "https://a.example.com",
        "https://b.example.com",
    ]


def test_cli_allowed_origin_defaults_to_none():
    """No flag means loopback-only, which is what a tunnel needs."""
    from paprika_mcp_server import cli

    seen = {}

    def _fake_run_http(host, port, allowed_origins):
        seen.update(allowed_origins=allowed_origins)

    with patch.object(sys, "argv", ["paprika-mcp", "serve-http"]), \
         patch("paprika_mcp_server.transports.http.run_http", _fake_run_http):
        cli.main()

    assert seen["allowed_origins"] is None


def test_run_http_closes_the_client_on_shutdown():
    """A long-running server must not leak the aiohttp session on shutdown."""
    from paprika_mcp_server.transports import http as http_mod

    client = MagicMock()
    client.close = AsyncMock()

    served = {}

    class _FakeUvicornServer:
        def __init__(self, config):
            served["config"] = config

        async def serve(self):
            served["ran"] = True

    with patch.object(http_mod, "build_runtime", AsyncMock(return_value=(client, None))), \
         patch.object(http_mod.uvicorn, "Server", _FakeUvicornServer):
        http_mod.run_http(host="127.0.0.1", port=9999)

    assert served.get("ran") is True
    assert served["config"].port == 9999
    client.close.assert_awaited_once()


def test_run_http_closes_the_client_when_serving_fails():
    from paprika_mcp_server.transports import http as http_mod

    client = MagicMock()
    client.close = AsyncMock()

    class _BoomServer:
        def __init__(self, config):
            pass

        async def serve(self):
            raise RuntimeError("port in use")

    with patch.object(http_mod, "build_runtime", AsyncMock(return_value=(client, None))), \
         patch.object(http_mod.uvicorn, "Server", _BoomServer):
        with pytest.raises(RuntimeError):
            http_mod.run_http()

    client.close.assert_awaited_once()
