"""Stateless streamable HTTP transport.

Serves the same tool surface as the stdio transport (see core/app.py) over
streamable HTTP so a remote agent can reach it. Authentication of HTTP
callers is deliberately out of scope here; the server binds loopback only
and exposure is the tunnel's job.
"""
import asyncio
import contextlib
import logging
from typing import Optional

import uvicorn
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.types import Receive, Scope, Send

from paprika_mcp_server.core.app import build_server
from paprika_mcp_server.image_generator import ImageGenerator
from paprika_mcp_server.paprika_client import PaprikaClient
from paprika_mcp_server.transports.stdio import build_runtime

logger = logging.getLogger(__name__)

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8080


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
) -> Starlette:
    """Build the ASGI app around an already-authenticated client.

    Stateless: every POST is self-contained, so there is no session or event
    store and a restart does not drop the client's connection.

    The caller owns `client`; this app never closes it. See run_http(), which
    creates the client and closes it when the server stops.
    """
    server = build_server(client, image_generator)
    session_manager = StreamableHTTPSessionManager(
        app=server,
        event_store=None,
        stateless=True,
        json_response=True,
    )

    async def healthz(request):
        return JSONResponse({"status": "ok"})

    @contextlib.asynccontextmanager
    async def lifespan(app):
        async with session_manager.run():
            logger.info("Streamable HTTP session manager started")
            yield

    return Starlette(
        routes=[
            # Route, never Mount. Measured: Mount("/mcp", ...) answers a POST
            # to /mcp with 307 -> /mcp/, and the redirect drops the POST body
            # and the Authorization header, which presents as an auth failure.
            Route(
                "/mcp",
                endpoint=_MCPEndpoint(session_manager),
                methods=["POST", "GET", "DELETE"],
            ),
            Route("/healthz", endpoint=healthz, methods=["GET"]),
        ],
        lifespan=lifespan,
    )


async def _serve(host: str, port: int) -> None:
    """Build the runtime and serve it, closing the client on shutdown.

    Everything runs in one event loop on purpose. The Paprika client owns an
    aiohttp session bound to the loop that created it, so building the client
    in a separate asyncio.run() and then handing it to uvicorn.run() (which
    starts a fresh loop) would leave every request talking to a closed loop.
    """
    client, image_generator = await build_runtime()
    try:
        app = build_app(client, image_generator)
        config = uvicorn.Config(app, host=host, port=port, log_level="info")
        await uvicorn.Server(config).serve()
    finally:
        # A long-running server must not leak the aiohttp session on shutdown.
        await client.close()


def run_http(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> None:
    """Serve over HTTP. Binds loopback only; exposure is the tunnel's job."""
    asyncio.run(_serve(host, port))
