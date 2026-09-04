"""stdio transport adapter."""
import logging
from typing import Optional, Tuple

from mcp.server import NotificationOptions
from mcp.server.models import InitializationOptions
from mcp.server.stdio import stdio_server

from paprika_mcp_server.config import get_config
from paprika_mcp_server.core.app import SERVER_NAME, SERVER_VERSION, build_server
from paprika_mcp_server.image_generator import ImageGenerator
from paprika_mcp_server.paprika_client import PaprikaClient

logger = logging.getLogger(__name__)


async def build_runtime() -> Tuple[PaprikaClient, Optional[ImageGenerator]]:
    """Load config, construct the client, authenticate. Transport-independent."""
    config = get_config()

    # Initialize ImageGenerator if API token is configured
    image_generator = None
    if config.replicate_api_token:
        try:
            image_generator = ImageGenerator(api_token=config.replicate_api_token)
            logger.info("AI image generation enabled (Replicate API)")
        except Exception as e:
            logger.warning(f"Failed to initialize ImageGenerator: {e}")
            logger.warning("AI image generation will be disabled")
    else:
        logger.info("Replicate API token not configured - AI image generation disabled")

    # Initialize Paprika client
    client = PaprikaClient(
        username=config.paprika_username,
        password=config.paprika_password,
        image_generator=image_generator,
    )
    try:
        await client.authenticate()
    except Exception:
        await client.close()
        raise
    logger.info("Successfully authenticated with Paprika")
    return client, image_generator


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
