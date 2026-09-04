"""Backwards-compatible entry point. The implementation lives in transports/."""
import asyncio

# Importing paprika_mcp_server.transports (the package, before its stdio
# submodule) configures INFO-level logging for all transports. See
# transports/__init__.py.
from paprika_mcp_server.transports.stdio import run_stdio


async def main() -> None:
    """Main entry point for the MCP server."""
    await run_stdio()


if __name__ == "__main__":
    asyncio.run(main())
