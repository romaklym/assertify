"""The relay end to end: MCP client over HTTP -> relay -> a fake phone app backed by Chromium."""

import asyncio
import base64
import json
import socket
import threading
import time

import pytest
import uvicorn
import websockets
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from playwright.async_api import async_playwright

from assertify.relay import app

from test_e2e import COOKIE, _ref, _text, site  # noqa: F401  (fixture: a small local test site)

TOKEN = "test-token-123"


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def relay():
    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(app(TOKEN), host="127.0.0.1", port=port, log_level="warning", ws="websockets-sansio"))
    t = threading.Thread(target=server.run, daemon=True)
    t.start()
    while not server.started:
        time.sleep(0.05)
    yield port
    server.should_exit = True
    t.join(5)


async def fake_phone(port: int, site_url: str, ready: asyncio.Event, token: str = TOKEN):
    """What the Flutter app does, with Playwright pages standing in for hidden WebViews."""
    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        ctx = await browser.new_context(viewport={"width": 390, "height": 844})
        await ctx.add_cookies([COOKIE])  # the user logged in earlier, in the app's visible browser
        pages = {}
        async with websockets.connect(f"ws://127.0.0.1:{port}/phone") as ws:
            sites = [{"name": "demo", "url": site_url, "domains": ["127.0.0.1"], "readOnly": False}]
            await ws.send(json.dumps({"type": "hello", "token": token, "device": "Test phone", "sites": sites}))
            welcome = json.loads(await ws.recv())
            if welcome.get("type") != "welcome":
                return
            ready.set()
            async for raw in ws:
                msg = json.loads(raw)
                op, a = msg["op"], msg["args"]
                try:
                    if op == "open":
                        pages[a["sid"]] = await ctx.new_page()
                        await pages[a["sid"]].goto(a["url"])
                        result = True
                    elif op == "close":
                        await pages.pop(a["sid"]).close()
                        result = True
                    elif op == "goto":
                        await pages[a["sid"]].goto(a["url"])
                        result = True
                    elif op == "back":
                        await pages[a["sid"]].go_back()
                        result = True
                    elif op == "wait":
                        await pages[a["sid"]].wait_for_load_state("domcontentloaded")
                        result = True
                    elif op == "events":
                        result = []
                    elif op == "state":
                        p = pages[a["sid"]]
                        result = {"url": p.url, "title": await p.title()}
                    elif op == "eval":
                        result = await pages[a["sid"]].evaluate(a["fn"], a["arg"])
                    elif op == "screenshot":
                        result = base64.b64encode(await pages[a["sid"]].screenshot(type="jpeg")).decode()
                    else:
                        raise ValueError(op)
                    await ws.send(json.dumps({"id": msg["id"], "ok": True, "result": result}))
                except Exception as e:
                    await ws.send(json.dumps({"id": msg["id"], "ok": False, "error": str(e)}))
        await browser.close()


async def _run(port: int, site_url: str) -> None:
    ready = asyncio.Event()
    phone = asyncio.create_task(fake_phone(port, site_url + "inbox", ready))
    await asyncio.wait_for(ready.wait(), 30)
    try:
        async with streamable_http_client(f"http://127.0.0.1:{port}/mcp/{TOKEN}") as (r, w), ClientSession(r, w) as s:
            await s.initialize()
            sites = _text(await s.call_tool("list_sites", {}))
            assert "demo" in sites

            snap = _text(await s.call_tool("open_session", {"site": "demo"}))
            assert "on Test phone" in snap and "Title:" in snap, snap
            sid = snap.split("session_id: ")[1].split()[0]

            await s.call_tool("type_text", {"session_id": sid, "ref": _ref(snap, "Search"), "text": "invoices"})
            res = await s.call_tool("click", {"session_id": sid, "ref": _ref(snap, 'button "Go"')})
            assert not res.is_error, _text(res)
            assert "Searched: invoices" in _text(await s.call_tool("read_text", {"session_id": sid}))

            shot = await s.call_tool("screenshot", {"session_id": sid})
            assert any(c.type == "image" for c in shot.content)

            stale = await s.call_tool("click", {"session_id": sid, "ref": "e999"})
            assert stale.is_error and "snapshot" in _text(stale)

            assert "Closed" in _text(await s.call_tool("close_session", {"session_id": sid}))
    finally:
        phone.cancel()


def test_relay_end_to_end(relay, site):  # noqa: F811
    asyncio.run(_run(relay, site))


def test_wrong_token_is_refused(relay):
    async def go():
        async with websockets.connect(f"ws://127.0.0.1:{relay}/phone") as ws:
            await ws.send(json.dumps({"type": "hello", "token": "nope"}))
            with pytest.raises(websockets.ConnectionClosed) as e:
                await ws.recv()
            assert e.value.rcvd.code == 4401

    asyncio.run(go())


def test_mcp_needs_the_secret_path(relay):
    import httpx2

    r = httpx2.post(f"http://127.0.0.1:{relay}/mcp/wrong", json={})
    assert r.status_code == 404


def test_no_phone_says_so(relay):
    async def go():
        async with streamable_http_client(f"http://127.0.0.1:{relay}/mcp/{TOKEN}") as (r, w), ClientSession(r, w) as s:
            await s.initialize()
            res = await s.call_tool("list_sites", {})
            assert res.is_error and "isn't connected" in _text(res)

    asyncio.run(go())
