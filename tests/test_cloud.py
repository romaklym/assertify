"""Assertify Cloud end to end: an AI app signs in with OAuth, the user links their computer with
`assertify link`, and tool calls run in the real local browser through `assertify connect`."""

import asyncio
import base64
import hashlib
import json
import secrets
import socket
import threading
import time
from urllib.parse import parse_qs, urlparse

import httpx2
import pytest
import uvicorn
import websockets
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from test_e2e import COOKIE, _ref, _text, site  # noqa: F401  (fixture: a small local test site)

from assertify import cloud, connect
from assertify.vault import Vault

REDIRECT = "http://127.0.0.1:9/callback"


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def server(monkeypatch, tmp_path):
    port = _free_port()
    base = f"http://127.0.0.1:{port}"
    monkeypatch.setenv("ASSERTIFY_CLOUD_URL", base)
    srv = uvicorn.Server(
        uvicorn.Config(
            cloud.app(base, str(tmp_path / "cloud.db")),
            host="127.0.0.1",
            port=port,
            log_level="warning",
            ws="websockets-sansio",
        )
    )
    t = threading.Thread(target=srv.run, daemon=True)
    t.start()
    while not srv.started:
        time.sleep(0.05)
    yield base
    srv.should_exit = True
    t.join(5)


def _sign_in(base: str, approve) -> dict:
    """What Claude or ChatGPT does: register, send the user to /authorize, swap the code for tokens."""
    with httpx2.Client(base_url=base) as h:
        meta = h.get("/.well-known/oauth-authorization-server").json()
        assert meta["registration_endpoint"].endswith("/register")
        client = h.post(
            "/register",
            json={"client_name": "Test AI", "redirect_uris": [REDIRECT], "token_endpoint_auth_method": "none"},
        ).json()
        verifier = secrets.token_urlsafe(48)
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
        r = h.get(
            "/authorize",
            params={
                "response_type": "code",
                "client_id": client["client_id"],
                "redirect_uri": REDIRECT,
                "code_challenge": challenge,
                "code_challenge_method": "S256",
                "state": "xyz",
                "scope": "assertify",
            },
        )
        assert r.status_code == 302, r.text
        link = r.headers["location"]
        req = parse_qs(urlparse(link).query)["req"][0]
        page = h.get(link).text
        code = page.split('class="code">')[1].split("<")[0]
        assert "Test AI" in page and h.get("/link/status", params={"req": req}).json()["redirect"] is None

        approve(code)  # the user runs `assertify link CODE` on their computer

        redirect = h.get("/link/status", params={"req": req}).json()["redirect"]
        q = parse_qs(urlparse(redirect).query)
        assert redirect.startswith(REDIRECT) and q["state"] == ["xyz"]
        tok = h.post(
            "/token",
            data={
                "grant_type": "authorization_code",
                "code": q["code"][0],
                "redirect_uri": REDIRECT,
                "client_id": client["client_id"],
                "code_verifier": verifier,
            },
        )
        assert tok.status_code == 200, tok.text
        return {**tok.json(), "client_id": client["client_id"]}


async def _use(base: str, token: str, site_url: str) -> None:
    async with (
        httpx2.AsyncClient(headers={"Authorization": f"Bearer {token}"}, timeout=60) as h,
        streamable_http_client(f"{base}/mcp", http_client=h) as (r, w),
        ClientSession(r, w) as s,
    ):
        await s.initialize()
        names = {t.name for t in (await s.list_tools()).tools}
        assert {"open_session", "click", "read_text"} <= names
        assert "demo" in _text(await s.call_tool("list_profiles", {}))

        snap = _text(await s.call_tool("open_session", {"profile": "demo"}))
        assert "Title: Inbox" in snap, snap
        sid = snap.split("session_id: ")[1].split()[0]
        await s.call_tool("type_text", {"session_id": sid, "ref": _ref(snap, "Search"), "text": "invoices"})
        res = await s.call_tool("click", {"session_id": sid, "ref": _ref(snap, 'button "Go"')})
        assert not res.is_error, _text(res)
        assert "Searched: invoices" in _text(await s.call_tool("read_text", {"session_id": sid}))
        shot = await s.call_tool("screenshot", {"session_id": sid})
        assert any(c.type == "image" for c in shot.content)
        await s.call_tool("close_session", {"session_id": sid, "save": False})


def test_cloud_end_to_end(server, site):  # noqa: F811
    Vault().save(
        "demo", {"cookies": [COOKIE], "origins": []}, {"start_url": site + "inbox", "allowed_domains": ["127.0.0.1"]}
    )
    tokens = _sign_in(server, lambda code: assert_ok(connect.link(code, yes=True)))

    async def go():
        comp = asyncio.create_task(connect.run_connect())
        try:
            for _ in range(100):  # wait for the companion's WebSocket
                if json.loads((await asyncio.to_thread(httpx2.get, f"{server}/healthz")).text.split()[1]):
                    break
                await asyncio.sleep(0.1)
            await asyncio.wait_for(_use(server, tokens["access_token"], site), 60)
        finally:
            comp.cancel()
            await asyncio.wait({comp}, timeout=15)  # let it close the browser before the loop ends

    asyncio.run(go())


def assert_ok(rc: int) -> None:
    assert rc == 0


def test_mcp_needs_a_token(server):
    r = httpx2.post(f"{server}/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    assert r.status_code == 401
    assert "resource_metadata" in r.headers["www-authenticate"]


def test_offline_computer_and_refresh(server):
    tokens = _sign_in(server, lambda code: assert_ok(connect.link(code, yes=True)))

    async def go():
        async with (
            httpx2.AsyncClient(headers={"Authorization": f"Bearer {tokens['access_token']}"}) as h,
            streamable_http_client(f"{server}/mcp", http_client=h) as (r, w),
            ClientSession(r, w) as s,
        ):
            await s.initialize()
            assert len((await s.list_tools()).tools) == len(cloud.default_tools())  # listed even when offline
            res = await s.call_tool("list_profiles", {})
            assert res.is_error and "assertify-mcp connect" in _text(res)

    asyncio.run(go())

    new = httpx2.post(
        f"{server}/token",
        data={
            "grant_type": "refresh_token",
            "refresh_token": tokens["refresh_token"],
            "client_id": tokens["client_id"],
        },
    )
    assert new.status_code == 200 and new.json()["access_token"] != tokens["access_token"]
    again = httpx2.post(  # the old refresh token was rotated out
        f"{server}/token",
        data={
            "grant_type": "refresh_token",
            "refresh_token": tokens["refresh_token"],
            "client_id": tokens["client_id"],
        },
    )
    assert again.status_code == 400

    assert connect.unlink() == 0  # revokes every app's access
    r = httpx2.post(
        f"{server}/mcp",
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
        headers={"Authorization": f"Bearer {new.json()['access_token']}"},
    )
    assert r.status_code == 401


def test_wrong_code_and_wrong_secret(server):
    assert connect.link("ZZZZ-ZZZZ", yes=True) == 1

    async def go():
        async with websockets.connect(server.replace("http", "ws") + "/device") as ws:
            await ws.send(json.dumps({"type": "hello", "device_id": "d_nope", "secret": "x", "tools": []}))
            with pytest.raises(websockets.ConnectionClosed) as e:
                await ws.recv()
            assert e.value.rcvd.code == 4401

    asyncio.run(go())


def test_bundled_tool_list_is_current():
    from assertify.server import mcp

    assert asyncio.run(connect._tools(mcp)) == cloud.default_tools(), "run scripts/gen_tools.py"
