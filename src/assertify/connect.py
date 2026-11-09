"""The companion: `assertify connect` links this computer to Assertify Cloud and runs its tool calls.

It keeps one outbound WebSocket to the cloud server (no open ports), sends the local tool list, and
runs each call in the local browser with the saved logins. Only tool calls and their results travel;
the logins and encryption key never leave this computer.

    assertify link ABCD-2345   # approve an AI app (the code comes from the app's sign-in page)
    assertify connect          # keep running so the AI apps can reach the browser
    assertify unlink           # forget this computer on the server and revoke every app's access
"""

from __future__ import annotations

import asyncio
import json
import os
import platform
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import websockets

from .vault import vault_home

DEFAULT_URL = "https://assertify.co"
MAX_FRAME = 32 * 1024 * 1024


def _http(method: str, path: str, body: dict | None = None, dev: dict | None = None) -> tuple[int, dict]:
    """A small JSON request to the cloud server; returns (status, json)."""
    req = urllib.request.Request(
        cloud_url() + path,
        method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type": "application/json", "User-Agent": "assertify-connect"},
    )
    if dev:
        req.add_header("Authorization", f"Device {dev['device_id']}:{dev['secret']}")
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read() or b"{}")
        except ValueError:
            return e.code, {"error": f"HTTP {e.code}"}


def cloud_url() -> str:
    return os.environ.get("ASSERTIFY_CLOUD_URL", DEFAULT_URL).rstrip("/")


def _cred_file() -> Path:
    return vault_home() / "cloud-device.json"


def load_device() -> dict | None:
    f = _cred_file()
    if not f.exists():
        return None
    data = json.loads(f.read_text())
    return data if data.get("url") == cloud_url() else None


def _save_device(data: dict) -> None:
    f = _cred_file()
    fd = os.open(f, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as fh:
        json.dump(data, fh)


def ensure_device() -> dict:
    """This computer's ID and secret on the server, registering it the first time."""
    dev = load_device()
    if dev:
        return dev
    name = platform.node() or "computer"
    status, data = _http("POST", "/device/register", {"name": name})
    if status != 200:
        raise RuntimeError(f"couldn't register this computer with {cloud_url()} (HTTP {status})")
    dev = {**data, "url": cloud_url(), "name": name}
    _save_device(dev)
    return dev


def link(code: str, yes: bool = False) -> int:
    dev = ensure_device()
    status, info = _http("GET", "/device/link?" + urllib.parse.urlencode({"code": code}), dev=dev)
    if status != 200:
        print(info.get("error", f"HTTP {status}"), file=sys.stderr)
        return 1
    print(
        f"{info['app']} (returns to {info['redirect_host']}) wants to use the browser and saved logins on this computer."
    )
    if not yes:
        if not sys.stdin.isatty():
            print("Run this in a terminal to confirm, or pass --yes.", file=sys.stderr)
            return 1
        if input("Allow it? [y/N] ").strip().lower() not in ("y", "yes"):
            print("Not linked.")
            return 1
    status, data = _http("POST", "/device/link", {"code": code}, dev=dev)
    if status != 200:
        print(data.get("error", f"HTTP {status}"), file=sys.stderr)
        return 1
    print("Linked. The app's sign-in page continues by itself.")
    print("Keep `uvx assertify-mcp connect` running whenever you want the app to use your browser.")
    return 0


def unlink() -> int:
    dev = load_device()
    if not dev:
        print("This computer isn't linked.")
        return 0
    status, _ = _http("POST", "/device/unlink", {}, dev=dev)
    if status not in (200, 401):
        print(f"The server answered {status}; try again.", file=sys.stderr)
        return 1
    _cred_file().unlink(missing_ok=True)
    print("Unlinked: every AI app linked to this computer lost access. Your saved logins are untouched.")
    return 0


async def _tools(mcp) -> list[dict]:
    return [t.model_dump(mode="json", by_alias=True, exclude_none=True) for t in await mcp.list_tools()]


async def _run_call(mcp, ws, send_lock: asyncio.Lock, msg: dict) -> None:
    from mcp.types import CallToolResult, TextContent

    try:
        result = await mcp.call_tool(msg["name"], msg.get("arguments") or {})
    except Exception as e:  # the same readable error the local server would return
        result = CallToolResult(content=[TextContent(type="text", text=str(e) or type(e).__name__)], is_error=True)
    reply = {"id": msg["id"], "ok": True, "result": result.model_dump(mode="json", by_alias=True, exclude_none=True)}
    async with send_lock:
        await ws.send(json.dumps(reply))


async def run_connect() -> None:
    from .server import manager, mcp

    dev = ensure_device()
    ws_url = cloud_url().replace("https://", "wss://").replace("http://", "ws://") + "/device"
    tools = await _tools(mcp)
    delay = 1.0
    print(f"Assertify: connecting this computer to {cloud_url()} ...", flush=True)
    try:
        while True:
            try:
                async with websockets.connect(ws_url, max_size=MAX_FRAME, ping_interval=20) as ws:
                    hello = {
                        "type": "hello",
                        "device_id": dev["device_id"],
                        "secret": dev["secret"],
                        "name": dev.get("name"),
                        "tools": tools,
                    }
                    await ws.send(json.dumps(hello))
                    welcome = json.loads(await ws.recv())
                    if welcome.get("type") != "welcome":
                        raise RuntimeError("unexpected answer from the server")
                    print(
                        "Connected. AI apps linked to this computer can use its browser now. Ctrl+C stops.", flush=True
                    )
                    delay = 1.0
                    lock, tasks = asyncio.Lock(), set()
                    async for raw in ws:
                        msg = json.loads(raw)
                        if msg.get("op") == "call":
                            t = asyncio.create_task(_run_call(mcp, ws, lock, msg))
                            tasks.add(t)
                            t.add_done_callback(tasks.discard)
            except websockets.InvalidStatus as e:
                print(f"The server refused the connection ({e.response.status_code}).", file=sys.stderr)
            except websockets.ConnectionClosed as e:
                if e.rcvd and e.rcvd.code == 4401:
                    sys.exit("This computer isn't known to the server any more. Run `assertify link CODE` again.")
                if e.rcvd and e.rcvd.code == 4000:
                    print("Another `assertify connect` took over for this computer.", file=sys.stderr)
                    return
                if e.rcvd and e.rcvd.code == 4001:
                    sys.exit("This computer was unlinked.")
                print("Disconnected; reconnecting...", file=sys.stderr, flush=True)
            except (OSError, RuntimeError, ValueError) as e:
                print(f"Can't reach {cloud_url()} ({e}); retrying...", file=sys.stderr, flush=True)
            await asyncio.sleep(delay)
            delay = min(delay * 2, 60)
    finally:
        await manager.shutdown()


def connect() -> int:
    try:
        asyncio.run(run_connect())
    except KeyboardInterrupt:
        print("\nStopped.")
    return 0
