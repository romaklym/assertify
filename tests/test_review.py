"""Reviewer demo: an app reviewer connects with a passphrase instead of a terminal and uses the
demo computer (`assertify demo`), which has a logged-in fake mail site."""

import asyncio
import json

import httpx2
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from test_cloud import _sign_in, server  # noqa: F401  (fixture)
from test_e2e import _ref, _text

from assertify import connect, demo
from assertify.vault import Vault

PASS = "review-pass-123"


def _approve_with_passphrase(base: str):
    def approve(_code: str, req: str) -> None:
        with httpx2.Client(base_url=base) as h:
            page = h.get("/link", params={"req": req}).text
            assert "Reviewing this app?" in page
            bad = h.post("/link/review", data={"req": req, "passphrase": "nope"})
            assert bad.status_code == 403
            ok = h.post("/link/review", data={"req": req, "passphrase": PASS})
            assert ok.status_code == 303, ok.text

    return approve


async def _review(base: str, token: str, site: str) -> None:
    async with (
        httpx2.AsyncClient(headers={"Authorization": f"Bearer {token}"}, timeout=60) as h,
        streamable_http_client(f"{base}/mcp", http_client=h) as (r, w),
        ClientSession(r, w) as s,
    ):
        await s.initialize()
        assert demo.PROFILE in _text(await s.call_tool("list_profiles", {}))
        snap = _text(await s.call_tool("open_session", {"profile": demo.PROFILE}))
        assert "Invoice 1042" in snap, snap
        sid = snap.split("session_id: ")[1].split()[0]

        await s.call_tool("type_text", {"session_id": sid, "ref": _ref(snap, "Search mail"), "text": "lunch"})
        snap = _text(await s.call_tool("click", {"session_id": sid, "text": "Search"}))
        assert "Lunch on Friday" in snap and "Invoice 1042" not in snap, snap

        snap = _text(
            await s.call_tool("navigate", {"session_id": sid, "url": site + "compose?to=marco@northwind.example"})
        )
        await s.call_tool("type_text", {"session_id": sid, "ref": _ref(snap, "Subject"), "text": "Lunch"})
        paused = await s.call_tool("click", {"session_id": sid, "ref": _ref(snap, 'button "Send"')})
        assert "confirmed=true" in _text(paused), _text(paused)  # sending waits for the user's OK
        await s.call_tool("navigate", {"session_id": sid, "url": site + "sent"})
        sent = _text(await s.call_tool("read_text", {"session_id": sid}))
        assert "Nothing sent yet" in sent, sent

        off = await s.call_tool("navigate", {"session_id": sid, "url": "https://example.com/"})
        assert off.is_error or "allowed" in _text(off).lower(), _text(off)  # locked to the demo site

        await s.call_tool("navigate", {"session_id": sid, "url": site + "reports"})
        csv = _text(await s.call_tool("download", {"session_id": sid, "text": "Download Q1 sales (CSV)"}))
        assert "March" in csv and "12400" in csv, csv
        await s.call_tool("close_session", {"session_id": sid, "save": False})


def test_reviewer_passphrase_and_demo(server, monkeypatch):  # noqa: F811
    # The tool server's browser manager lives for the whole test run; give it this test's vault.
    from assertify import server as tool_server

    monkeypatch.setattr(tool_server.manager, "vault", Vault())
    url = demo.start_site()
    demo.save_profile(url)
    dev = connect.ensure_device()
    monkeypatch.setenv("ASSERTIFY_REVIEW_PASSPHRASE", PASS)
    monkeypatch.setenv("ASSERTIFY_REVIEW_DEVICE", dev["device_id"])
    tokens = _sign_in(server, _approve_with_passphrase(server))

    async def go():
        comp = asyncio.create_task(connect.run_connect())
        try:
            for _ in range(100):
                if json.loads((await asyncio.to_thread(httpx2.get, f"{server}/healthz")).text.split()[1]):
                    break
                await asyncio.sleep(0.1)
            await asyncio.wait_for(_review(server, tokens["access_token"], url), 90)
        finally:
            comp.cancel()
            await asyncio.wait({comp}, timeout=15)

    asyncio.run(go())


def test_review_disabled_by_default(server):  # noqa: F811
    with httpx2.Client(base_url=server) as h:
        r = h.post("/link/review", data={"req": "x", "passphrase": "y"})
        assert r.status_code == 404
