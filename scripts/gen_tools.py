"""Write src/assertify/tools.json: the companion's tool list, served by the cloud before a computer links."""

import asyncio
import json
from pathlib import Path

from assertify.connect import _tools
from assertify.server import mcp

out = Path(__file__).resolve().parent.parent / "src" / "assertify" / "tools.json"
out.write_text(json.dumps(asyncio.run(_tools(mcp)), indent=1) + "\n")
print(f"wrote {out}")
