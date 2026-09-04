"""Stateless streamable HTTP transport.

Serves the same tool surface as the stdio transport (see core/app.py) over
streamable HTTP so a remote agent can reach it. Authentication of HTTP
callers is deliberately out of scope here; the server binds loopback only
and exposure is the tunnel's job.
"""
import asyncio
import contextlib
import logging
from typing import Iterable, Optional, Sequence
from urllib.parse import urlsplit

import uvicorn
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from starlette.applications import Starlette
from starlette.datastructures import Headers
from starlette.middleware import Middleware
from starlette.responses import JSONResponse, Response
from starlette.routing import Route
from starlette.types import ASGIApp, Receive, Scope, Send

from paprika_mcp_server.core.app import build_server
from paprika_mcp_server.image_generator import ImageGenerator
from paprika_mcp_server.paprika_client import PaprikaClient
from paprika_mcp_server.transports.runtime import build_runtime

logger = logging.getLogger(__name__)

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8080

# Origins always accepted without being named on the command line: a browser
# page served from the same machine (MCP Inspector, a local dev UI).
LOOPBACK_ORIGIN_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})


def _is_loopback_origin(origin: str) -> bool:
    try:
        return urlsplit(origin).hostname in LOOPBACK_ORIGIN_HOSTS
    except ValueError:
        return False


class OriginValidationMiddleware:
    """Reject cross-origin browser requests (DNS-rebinding defence).

    Host validation is deliberately NOT performed. cloudflared forwards
    `Host: <random>.trycloudflare.com`, so a host allowlist would reject the
    tunnel with a confusing 421 -- which is why this does not use the mcp
    package's TransportSecuritySettings: enabling its DNS-rebinding
    protection turns on Host checking too, and an empty allowed_hosts list
    rejects everything.

    Origin is the header that actually separates an attacker's page from a
    legitimate caller, because a browser sets it and a script cannot forge it:

      * absent Origin  -> allowed. Non-browser callers send none; this is how
        Claude reaches the server, over the tunnel or directly.
      * loopback Origin -> allowed (see LOOPBACK_ORIGIN_HOSTS).
      * anything else  -> 403, unless named via --allowed-origin.

    Without this, a DNS-rebinding attack can make an attacker's page
    same-origin with 127.0.0.1:8080 and reach
    clear_grocery_list, which are unauthenticated in this phase.
    """

    def __init__(self, app: ASGIApp, allowed_origins: Sequence[str] = ()) -> None:
        self.app = app
        self.allowed_origins = tuple(allowed_origins)

    def _is_allowed(self, origin: str) -> bool:
        return origin in self.allowed_origins or _is_loopback_origin(origin)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        origin = Headers(scope=scope).get("origin")
        if origin and not self._is_allowed(origin):
            logger.warning("Rejected request with disallowed Origin: %s", origin)
            response = Response("Invalid Origin header", status_code=403)
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)


class _MCPEndpoint:
    """ASGI endpoint delegating to the streamable HTTP session manager.

    Must be a callable INSTANCE, not a plain function. Starlette's Route
    checks inspect.isfunction(endpoint) and, for a function, wraps it as
    endpoint(request) -> response. A raw ASGI function therefore raises
    "missing 2 required positional arguments: 'receive' and 'send'".
    An instance is treated as an ASGI app and called (scope, receive, send).
    """

    def __init__(self, manager: StreamableHTTPSessionManager) -> None:
        self._manager = manager

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        await self._manager.handle_request(scope, receive, send)


def build_app(
    client: PaprikaClient,
    image_generator: Optional[ImageGenerator] = None,
    allowed_origins: Optional[Iterable[str]] = None,
) -> Starlette:
    """Build the ASGI app around an already-authenticated client.

    Stateless: every POST is self-contained, so there is no session or event
    store and a restart does not drop the client's connection.

    The caller owns `client`; this app never closes it. See run_http(), which
    creates the client and closes it when the server stops.

    `allowed_origins` extends the browser origins accepted by
    OriginValidationMiddleware beyond loopback. Requests with no Origin
    header are always accepted, so a cloudflared tunnel keeps working.
    """
    server = build_server(client, image_generator)
    session_manager = StreamableHTTPSessionManager(
        app=server,
        event_store=None,
        stateless=True,
        json_response=True,
    )
    mcp_endpoint = _MCPEndpoint(session_manager)

    async def healthz(request):
        return JSONResponse({"status": "ok"})

    @contextlib.asynccontextmanager
    async def lifespan(app):
        async with session_manager.run():
            logger.info("Streamable HTTP session manager started")
            yield

    return Starlette(
        routes=[
            # Two routes, same _MCPEndpoint instance (same session_manager),
            # to dodge two different redirects. Measured against this app:
            #   Mount("/mcp", ...) answers POST /mcp with 307 -> /mcp/.
            #   A single Route("/mcp", ...) answers POST /mcp/ with
            #     307 -> /mcp (Starlette's redirect_slashes is on by default
            #     and there is no supported way to turn it off here:
            #     Starlette(..., redirect_slashes=False) raises TypeError).
            # Either direction drops the POST body and the Authorization
            # header on the redirect, which is a silent MCP failure today and
            # will present as a confusing auth failure once OAuth lands. Do
            # not delete the second route as "redundant" -- it is what stops
            # the second redirect.
            Route(
                "/mcp",
                endpoint=mcp_endpoint,
                methods=["POST", "GET", "DELETE"],
            ),
            Route(
                "/mcp/",
                endpoint=mcp_endpoint,
                methods=["POST", "GET", "DELETE"],
            ),
            Route("/healthz", endpoint=healthz, methods=["GET"]),
        ],
        middleware=[
            Middleware(
                OriginValidationMiddleware,
                allowed_origins=tuple(allowed_origins or ()),
            )
        ],
        lifespan=lifespan,
    )


async def _serve(
    host: str, port: int, allowed_origins: Optional[Iterable[str]] = None
) -> None:
    """Build the runtime and serve it, closing the client on shutdown.

    Everything runs in one event loop on purpose. The Paprika client owns an
    aiohttp session bound to the loop that created it, so building the client
    in a separate asyncio.run() and then handing it to uvicorn.run() (which
    starts a fresh loop) would leave every request talking to a closed loop.
    """
    client, image_generator = await build_runtime()
    try:
        app = build_app(client, image_generator, allowed_origins=allowed_origins)
        config = uvicorn.Config(app, host=host, port=port, log_level="info")
        await uvicorn.Server(config).serve()
    finally:
        # A long-running server must not leak the aiohttp session on shutdown.
        await client.close()


def run_http(
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    allowed_origins: Optional[Iterable[str]] = None,
) -> None:
    """Serve over HTTP. Binds loopback only; exposure is the tunnel's job."""
    asyncio.run(_serve(host, port, allowed_origins))
