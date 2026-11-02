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
<button onclick="if (confirm('Really delete?')) document.getElementById('out').textContent='Deleted'">Delete all</button>
<input placeholder="Write a message" id="msg">
"""

PAGES = {
    "/popup": b"""<!doctype html><title>Feed</title>
<h1>Your feed</h1><button onclick="document.body.dataset.liked=1">Like</button>
<div id="ov" style="position:fixed;inset:0;background:rgba(0,0,0,.5);z-index:9">
<div role="dialog" aria-label="Share your contact info" style="margin:20vh auto;width:50%;background:#fff">
  <h2>Share your contact info?</h2><button>Share</button>
  <button onclick="document.getElementById('ov').remove()">Not now</button>
</div></div>""",
    "/cookies": b"""<!doctype html><title>News</title><h1>News</h1>
<div style="position:fixed;bottom:0;left:0;right:0;background:#eee" id="cb">
  We use cookies to improve your experience.
  <button onclick="document.getElementById('cb').remove()">Accept all</button>
  <button onclick="document.getElementById('cb').remove(); document.title='Rejected'">Reject all</button>
</div>""",
    "/signin": b"""<!doctype html><title>Sign in</title>
<input name="user"><input type="password" name="pw"><button>Sign in</button>""",
}


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
        self.wfile.write(PAGES.get(self.path, PAGE))

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


COOKIE = {
    "name": "session",
    "value": "ok",
    "domain": "127.0.0.1",
    "path": "/",
    "expires": -1,
    "httpOnly": True,
    "secure": False,
    "sameSite": "Lax",
}


async def _run(url: str) -> None:
    Vault().save("demo", {"cookies": [COOKIE], "origins": []}, {"start_url": url, "allowed_domains": ["127.0.0.1"]})

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

        local = await s.call_tool("navigate", {"session_id": sid, "url": "file:///etc/passwd"})
        assert local.is_error and "http(s)" in _text(local)

        # Risky buttons pause until confirmed; the JS confirm() box is cancelled unless asked.
        risky = await s.call_tool("click", {"session_id": sid, "text": "Delete all"})
        assert risky.is_error and "confirmed=true" in _text(risky)
        res = _text(await s.call_tool("click", {"session_id": sid, "text": "Delete all", "confirmed": True}))
        assert "confirm box" in res and "Really delete?" in res and "dismissed" in res, res
        res = await s.call_tool(
            "click", {"session_id": sid, "text": "Delete all", "confirmed": True, "accept_dialog": True}
        )
        assert "Deleted" in _text(await s.call_tool("read_text", {"session_id": sid}))

        # Enter in a non-search field may send something.
        send = await s.call_tool(
            "type_text", {"session_id": sid, "label": "Write a message", "text": "hi", "submit": True}
        )
        assert send.is_error and "confirmed=true" in _text(send)

        # Pop-ups are listed first and flagged; clicks under them are refused; dismiss_popup closes them.
        snap = _text(await s.call_tool("navigate", {"session_id": sid, "url": url + "popup"}))
        assert "Pop-up open" in snap and "Share your contact info" in snap, snap
        assert snap.index("## Pop-up") < snap.index("## Page")
        covered = await s.call_tool("click", {"session_id": sid, "text": "Like"})
        assert covered.is_error and "dismiss_popup" in _text(covered), _text(covered)
        snap = _text(await s.call_tool("dismiss_popup", {"session_id": sid}))
        assert "Not now" in snap and "Pop-up open" not in snap, snap

        # Cookie banners get the privacy-friendly answer automatically.
        snap = _text(await s.call_tool("navigate", {"session_id": sid, "url": url + "cookies"}))
        assert "Declined a cookie banner" in snap and "Title: Rejected" in snap, snap

        # Sign-in pages are flagged so the agent hands off instead of typing a password.
        snap = _text(await s.call_tool("navigate", {"session_id": sid, "url": url + "signin"}))
        assert "sign-in page" in snap and "handoff" in snap, snap

        found = _text(await s.call_tool("find", {"session_id": sid, "query": "sign in"}))
        assert 'button "Sign in"' in found

        await s.call_tool("close_session", {"session_id": sid})


def test_agent_session_end_to_end(site):
    asyncio.run(asyncio.wait_for(_run(site), timeout=90))


async def _read_only(url: str) -> None:
    Vault().save(
        "ro",
        {"cookies": [COOKIE], "origins": []},
        {"start_url": url + "signin", "allowed_domains": ["127.0.0.1"], "read_only": True},
    )
    params = StdioServerParameters(command=sys.executable, args=["-m", "assertify", "serve"], env=dict(os.environ))
    async with stdio_client(params) as (r, w), ClientSession(r, w) as s:
        await s.initialize()
        snap = _text(await s.call_tool("open_session", {"profile": "ro"}))
        sid = snap.splitlines()[0].split(": ")[1]
        assert "Mode: read-only" in snap
        typed = await s.call_tool("type_text", {"session_id": sid, "label": "user", "text": "x"})
        assert typed.is_error and "read-only" in _text(typed)
        await s.call_tool("close_session", {"session_id": sid, "save": False})


def test_read_only_profile(site):
    asyncio.run(asyncio.wait_for(_read_only(site), timeout=60))


def test_humanized_session(site, monkeypatch):
    """Same flow with random pauses, curved mouse moves and per-key typing turned on."""
    monkeypatch.setenv("ASSERTIFY_HUMANIZE", "1")

    async def run():
        Vault().save(
            "h",
            {"cookies": [COOKIE], "origins": []},
            {"start_url": url_ + "popup", "allowed_domains": ["127.0.0.1"]},
        )
        params = StdioServerParameters(command=sys.executable, args=["-m", "assertify", "serve"], env=dict(os.environ))
        async with stdio_client(params) as (r, w), ClientSession(r, w) as s:
            await s.initialize()
            snap = _text(await s.call_tool("open_session", {"profile": "h"}))
            sid = snap.splitlines()[0].split(": ")[1]
            await s.call_tool("dismiss_popup", {"session_id": sid})
            await s.call_tool("click", {"session_id": sid, "text": "Like"})
            ua = await s.call_tool("read_text", {"session_id": sid})
            assert not ua.is_error
            await s.call_tool("close_session", {"session_id": sid, "save": False})

    url_ = site
    asyncio.run(asyncio.wait_for(run(), timeout=90))
