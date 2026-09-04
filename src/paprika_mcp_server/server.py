import asyncio
import logging

from mcp.server import NotificationOptions
from mcp.server.models import InitializationOptions
from mcp.server.stdio import stdio_server

from paprika_mcp_server.config import get_config
from paprika_mcp_server.core.app import build_server
from paprika_mcp_server.image_generator import ImageGenerator
from paprika_mcp_server.paprika_client import PaprikaClient

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def main():
    """Main entry point for the MCP server."""
    paprika_client = None
    try:
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
        paprika_client = PaprikaClient(
            username=config.paprika_username,
            password=config.paprika_password,
            image_generator=image_generator
        )
        await paprika_client.authenticate()
        logger.info("Successfully authenticated with Paprika")

        # Wire the tool surface to a Server
        server = build_server(paprika_client, image_generator)

        # Run the server
        async with stdio_server() as (read_stream, write_stream):
            await server.run(
                read_stream,
                write_stream,
                InitializationOptions(
                    server_name="paprika-mcp-python",
                    server_version="1.0.0",
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
        if paprika_client:
            await paprika_client.close()


if __name__ == "__main__":
    asyncio.run(main())
