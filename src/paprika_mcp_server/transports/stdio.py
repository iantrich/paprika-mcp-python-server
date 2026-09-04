"""stdio transport adapter."""
import logging

from mcp.server import NotificationOptions
from mcp.server.models import InitializationOptions
from mcp.server.stdio import stdio_server

from paprika_mcp_server.core.app import SERVER_NAME, SERVER_VERSION, build_server
from paprika_mcp_server.transports.runtime import build_runtime

logger = logging.getLogger(__name__)


async def run_stdio() -> None:
    """Run the MCP server over stdio."""
    client = None
    try:
        client, image_generator = await build_runtime()

        # Wire the tool surface to a Server
        server = build_server(client, image_generator)

        # Run the server
        async with stdio_server() as (read_stream, write_stream):
            await server.run(
                read_stream,
                write_stream,
                InitializationOptions(
                    server_name=SERVER_NAME,
                    server_version=SERVER_VERSION,
                    capabilities=server.get_capabilities(
                        notification_options=NotificationOptions(),
                        experimental_capabilities={},
                    ),
                ),
            )

    except Exception as e:
        logger.error(f"Server startup failed: {str(e)}")
        raise
    finally:
        if client:
            await client.close()
