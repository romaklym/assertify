"""A login window in the user's own, un-automated Chrome.

Google (and some other sign-in providers) refuse to sign in inside a browser that an automation tool
is driving. So for logins Assertify starts the installed Chrome as a normal app, with a throwaway
profile folder and a DevTools port on 127.0.0.1 (a pipe would make Chrome flag itself as automated,
navigator.webdriver = true). While the user signs in,
it only asks the browser for its cookie jar, which pages can't see. Pages are read (localStorage,
which account is signed in) once, after the user says they are done. Then Chrome is closed and the
throwaway profile is deleted.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

import websockets


def find_chrome() -> str | None:
    """Path of an installed Chrome (or Chromium / Edge), or None."""
    env = os.environ.get("ASSERTIFY_CHROME_PATH")
    if env:
        return env if Path(env).exists() else None
    if sys.platform == "darwin":
        names = ["Google Chrome", "Chromium", "Microsoft Edge"]
        for base in ("/Applications", str(Path.home() / "Applications")):
            for n in names:
                p = Path(base) / f"{n}.app" / "Contents" / "MacOS" / n
                if p.exists():
                    return str(p)
        return None
    if sys.platform == "win32":
        roots = [os.environ.get(k) for k in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA")]
        for root in filter(None, roots):
            for rel in (r"Google\Chrome\Application\chrome.exe", r"Microsoft\Edge\Application\msedge.exe"):
                p = Path(root) / rel
                if p.exists():
                    return str(p)
        return None
    for n in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "microsoft-edge"):
        p = shutil.which(n)
        if p:
            return p
    return None


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _ws_url(port: int) -> str:
    with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=2) as r:
        return json.loads(r.read())["webSocketDebuggerUrl"]


def native_supported() -> bool:
    """ASSERTIFY_LOGIN_WINDOW=playwright goes back to the automated login window."""
    return os.environ.get("ASSERTIFY_LOGIN_WINDOW", "").lower() != "playwright"


def _to_cdp(c: dict) -> dict:
    out = {k: c[k] for k in ("name", "value", "domain", "path", "httpOnly", "secure") if k in c}
    if c.get("expires", -1) not in (-1, None):
        out["expires"] = c["expires"]
    if c.get("sameSite") in ("Strict", "Lax", "None"):
        out["sameSite"] = c["sameSite"]
    return out


def _from_cdp(c: dict) -> dict:
    return {
        "name": c["name"],
        "value": c["value"],
        "domain": c["domain"],
        "path": c.get("path", "/"),
        "expires": -1 if c.get("session") else c.get("expires", -1),
        "httpOnly": bool(c.get("httpOnly")),
        "secure": bool(c.get("secure")),
        "sameSite": c.get("sameSite") if c.get("sameSite") in ("Strict", "Lax", "None") else "Lax",
    }


class NativeChrome:
    """One Chrome process with a throwaway profile and a local DevTools port."""

    def __init__(self) -> None:
        self.proc: subprocess.Popen | None = None
        self.user_dir: str | None = None
        self._ws = None
        self._reader_task: asyncio.Task | None = None
        self._next = 0
        self._waiting: dict[int, asyncio.Future] = {}
        self.closed = asyncio.Event()

    async def start(self, chrome: str, url: str, cookies: list[dict] | None) -> None:
        self.user_dir = tempfile.mkdtemp(prefix="assertify-login-")  # 0700: only this user can read it
        port = _free_port()
        self.proc = subprocess.Popen(
            [
                chrome,
                f"--user-data-dir={self.user_dir}",
                "--remote-debugging-address=127.0.0.1",
                # A fixed port: with port 0 or a pipe Chrome marks itself as automated (navigator.webdriver).
                f"--remote-debugging-port={port}",
                "--no-first-run",
                "--no-default-browser-check",
                "--new-window",
                "about:blank",
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        ws_url = None
        for _ in range(150):
            if self.proc.poll() is not None:
                raise RuntimeError("Chrome exited right after starting.")
            try:
                ws_url = await asyncio.to_thread(_ws_url, port)
                break
            except OSError:
                await asyncio.sleep(0.1)
        if not ws_url:
            raise RuntimeError("Chrome didn't open its DevTools port.")
        self._ws = await websockets.connect(ws_url, max_size=None, open_timeout=10)
        self._reader_task = asyncio.create_task(self._reader())

        if cookies:
            await self.send("Storage.setCookies", {"cookies": [_to_cdp(c) for c in cookies]})
        blank = [t["targetId"] for t in await self.page_targets()]
        await self.send("Target.createTarget", {"url": url})
        for tid in blank:  # drop the empty first tab
            await self.send("Target.closeTarget", {"targetId": tid})

    async def _reader(self) -> None:
        try:
            async for msg in self._ws:
                try:
                    data = json.loads(msg)
                except ValueError:
                    continue
                fut = self._waiting.pop(data.get("id"), None)
                if fut and not fut.done():
                    if "error" in data:
                        fut.set_exception(RuntimeError(data["error"].get("message", "CDP error")))
                    else:
                        fut.set_result(data.get("result", {}))
        except Exception:
            pass
        self.closed.set()
        for fut in self._waiting.values():
            if not fut.done():
                fut.set_exception(RuntimeError("The browser was closed."))
        self._waiting.clear()

    async def send(self, method: str, params: dict | None = None, session: str | None = None) -> dict:
        if self.closed.is_set() or self._ws is None:
            raise RuntimeError("The browser was closed.")
        self._next += 1
        msg = {"id": self._next, "method": method, "params": params or {}}
        if session:
            msg["sessionId"] = session
        fut = asyncio.get_running_loop().create_future()
        self._waiting[self._next] = fut
        try:
            await self._ws.send(json.dumps(msg))
        except Exception as e:
            self._waiting.pop(self._next, None)
            raise RuntimeError("The browser was closed.") from e
        return await asyncio.wait_for(fut, timeout=15)

    # ---- while the user signs in: browser-level calls only, nothing a page can notice ----

    async def cookies(self) -> list[dict]:
        res = await self.send("Storage.getCookies")
        return [_from_cdp(c) for c in res.get("cookies", [])]

    async def page_targets(self) -> list[dict]:
        res = await self.send("Target.getTargets")
        return [t for t in res.get("targetInfos", []) if t.get("type") == "page"]

    async def bring_to_front(self) -> None:
        pages = await self.page_targets()
        if pages:
            await self.send("Target.activateTarget", {"targetId": pages[-1]["targetId"]})

    async def user_agent(self) -> str:
        return (await self.send("Browser.getVersion")).get("userAgent", "")

    # ---- after the user is done ----

    async def evaluate_pages(self, expression: str, skip=None) -> list[tuple[str, object]]:
        """Run JS in every open web tab, except those `skip(url)` picks: [(url, value)]."""
        out = []
        for t in await self.page_targets():
            if not t.get("url", "").startswith("http") or (skip and skip(t["url"])):
                continue
            try:
                sid = (await self.send("Target.attachToTarget", {"targetId": t["targetId"], "flatten": True}))[
                    "sessionId"
                ]
                res = await self.send(
                    "Runtime.evaluate",
                    {"expression": expression, "returnByValue": True, "awaitPromise": True},
                    session=sid,
                )
                out.append((t["url"], res.get("result", {}).get("value")))
                await self.send("Target.detachFromTarget", {"sessionId": sid})
            except Exception:
                continue
        return out

    async def close(self) -> None:
        if self.proc and self.proc.poll() is None:
            try:
                await self.send("Browser.close")
            except Exception:
                pass
            for _ in range(30):
                if self.proc.poll() is not None:
                    break
                await asyncio.sleep(0.1)
            if self.proc.poll() is None:
                self.proc.kill()
        if self._ws is not None:
            try:
                await self._ws.close()
            except Exception:
                pass
        if self._reader_task:
            self._reader_task.cancel()
        if self.user_dir:  # the throwaway profile holds the session in plain form: remove it
            await asyncio.to_thread(shutil.rmtree, self.user_dir, True)
            self.user_dir = None
