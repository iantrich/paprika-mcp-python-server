"""Dump the MCP tool schemas registered by server.main() to JSON.

The tool definitions live inside main(), so they cannot simply be imported.
This runs main() far enough to register them, with authentication stubbed
out and the transport short-circuited, then serialises what was registered.
"""
import asyncio
import json
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

os.environ.setdefault("PAPRIKA_USERNAME", "snapshot@example.com")
os.environ.setdefault("PAPRIKA_PASSWORD", "snapshot")
os.environ.pop("REPLICATE_API_TOKEN", None)

import paprika_mcp_server.server as srv  # noqa: E402


class _StopBeforeTransport(Exception):
    """Raised to unwind main() once the handlers are registered."""


def capture():
    captured = {}
    original_list_tools = srv.server.list_tools

    def capturing_list_tools():
        real_decorator = original_list_tools()

        def wrapper(fn):
            captured["list_tools"] = fn
            return real_decorator(fn)

        return wrapper

    srv.server.list_tools = capturing_list_tools

    def _boom(*args, **kwargs):
        raise _StopBeforeTransport()

    async def _run():
        with patch.object(
            srv.PaprikaClient, "authenticate", new_callable=AsyncMock
        ), patch.object(srv, "stdio_server", _boom):
            try:
                await srv.main()
            except _StopBeforeTransport:
                pass

    asyncio.run(_run())

    if "list_tools" not in captured:
        raise SystemExit("list_tools handler was never registered")

    tools = asyncio.run(captured["list_tools"]())
    return sorted(
        (t.model_dump(mode="json", exclude_none=True) for t in tools),
        key=lambda d: d["name"],
    )


if __name__ == "__main__":
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("tests/fixtures/tool_schemas.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    schemas = capture()
    out.write_text(json.dumps(schemas, indent=2, sort_keys=True) + "\n")
    print(f"wrote {len(schemas)} tool schemas to {out}")
