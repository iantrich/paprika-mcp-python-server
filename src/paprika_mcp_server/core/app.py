"""Builds the MCP Server object. The only module that touches it."""
from typing import Optional

from mcp.server.lowlevel import Server
from mcp.types import TextContent, Tool

from paprika_mcp_server.core.handlers import dispatch
from paprika_mcp_server.core.tools import TOOLS
from paprika_mcp_server.image_generator import ImageGenerator
from paprika_mcp_server.paprika_client import PaprikaClient

SERVER_NAME = "paprika-mcp-python"
SERVER_VERSION = "1.0.0"


def build_server(
    client: PaprikaClient,
    image_generator: Optional[ImageGenerator] = None,
) -> Server:
    """Wire the tool surface to a Server. Transport-agnostic."""
    server = Server(SERVER_NAME)

    @server.list_tools()
    async def handle_list_tools() -> list[Tool]:
        return TOOLS

    @server.call_tool()
    async def handle_call_tool(
        name: str, arguments: dict
    ) -> list[TextContent]:
        return await dispatch(name, arguments, client, image_generator)

    return server
