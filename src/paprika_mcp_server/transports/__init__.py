"""Transport adapters over the shared core."""
import logging

# Configure INFO-level logging for every transport (stdio, and future
# transports such as HTTP) that imports a module from this package. This
# used to live only in server.py's module body, which meant it only ran
# when paprika_mcp_server.server was imported; a transport imported
# directly (e.g. by an HTTP entry point that never imports server.py)
# would silently fall back to the root logger's default WARNING level.
logging.basicConfig(level=logging.INFO)
