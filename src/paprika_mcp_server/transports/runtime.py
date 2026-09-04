"""Transport-independent runtime construction.

Lives outside any single transport on purpose: both stdio and HTTP (and a
future authenticated transport) need this, and importing it from
transports/stdio.py dragged mcp.server.stdio into every HTTP start.
"""
import logging
from typing import Optional, Tuple

from paprika_mcp_server.config import get_config
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
