"""Backwards-compatible entry point. The implementation lives in transports/."""
import asyncio
import logging

from paprika_mcp_server.transports.stdio import run_stdio

logging.basicConfig(level=logging.INFO)


async def main() -> None:
    """Main entry point for the MCP server."""
    await run_stdio()


if __name__ == "__main__":
    asyncio.run(main())
