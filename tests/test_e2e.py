"""Drive the real MCP server over stdio against a tiny local site. Needs Chromium (`assertify setup`)."""

import asyncio
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from assertify.vault import Vault

PAGE = b"""<!doctype html><title>Inbox</title>
<h1>Hello, tester</h1>
<input placeholder="Search" id="q">
<select id="f"><option>All</option><option>Unread</option></select>
<button onclick="document.getElementById('out').textContent='Searched: '+document.getElementById('q').value">Go</button>
<p id="out"></p>
<a href="https://example.com/">Leave the site</a>
"""


class Site(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.headers.get("Cookie", "").find("session=ok") < 0:
            self.send_response(302)
            self.send_header("Location", "/login")
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(PAGE)

    def log_message(self, *args):
        pass


@pytest.fixture
def site():
    server = ThreadingHTTPServer(("127.0.0.1", 0), Site)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}/"
    server.shutdown()


def _text(result) -> str:
    return "\n".join(c.text for c in result.content if c.type == "text")


def _ref(snapshot: str, needle: str) -> str:
    line = next(line for line in snapshot.splitlines() if needle in line)
    return line.split("]")[0].strip("[")


async def _run(url: str) -> None:
    cookie = {
        "name": "session",
        "value": "ok",
        "domain": "127.0.0.1",
        "path": "/",
        "expires": -1,
        "httpOnly": True,
        "secure": False,
        "sameSite": "Lax",
    }
    Vault().save("demo", {"cookies": [cookie], "origins": []}, {"start_url": url, "allowed_domains": ["127.0.0.1"]})

    params = StdioServerParameters(command=sys.executable, args=["-m", "assertify", "serve"], env=dict(os.environ))
    async with stdio_client(params) as (r, w), ClientSession(r, w) as s:
        init = await s.initialize()
        assert init.server_info.title == "Assertify"
        assert init.server_info.icons

        res = await s.call_tool("open_session", {"profile": "demo"})
        snap = _text(res)
        assert "Title: Inbox" in snap, snap  # the saved cookie got us past the login redirect
        sid = snap.splitlines()[0].split(": ")[1]

        await s.call_tool("type_text", {"session_id": sid, "ref": _ref(snap, "Search"), "text": "invoices"})
        await s.call_tool("select_option", {"session_id": sid, "ref": _ref(snap, "combobox"), "option": "Unread"})
        await s.call_tool("click", {"session_id": sid, "ref": _ref(snap, 'button "Go"')})
        assert "Searched: invoices" in _text(await s.call_tool("read_text", {"session_id": sid}))

        shot = await s.call_tool("screenshot", {"session_id": sid})
        assert any(c.type == "image" and c.mime_type == "image/jpeg" for c in shot.content)

        blocked = await s.call_tool("navigate", {"session_id": sid, "url": "https://example.com/"})
        assert "Blocked" in _text(blocked)

        stale = await s.call_tool("click", {"session_id": sid, "ref": "e999"})
        assert stale.is_error and "snapshot" in _text(stale)

        await s.call_tool("close_session", {"session_id": sid})


def test_agent_session_end_to_end(site):
    asyncio.run(asyncio.wait_for(_run(site), timeout=90))
