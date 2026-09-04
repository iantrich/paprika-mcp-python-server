"""Dump the MCP tool schemas to JSON.

The definitions now live in paprika_mcp_server.core.tools, so they can be
imported directly — no need to run main() with authentication stubbed out.
Serialisation is unchanged, so the output is comparable to snapshots taken
before the extraction.
"""
import json
import sys
from pathlib import Path

from paprika_mcp_server.core.tools import TOOLS


def capture():
    return sorted(
        (t.model_dump(mode="json", exclude_none=True) for t in TOOLS),
        key=lambda d: d["name"],
    )


if __name__ == "__main__":
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("tests/fixtures/tool_schemas.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    schemas = capture()
    out.write_text(json.dumps(schemas, indent=2, sort_keys=True) + "\n")
    print(f"wrote {len(schemas)} tool schemas to {out}")
