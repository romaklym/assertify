"""Playwright session manager: headed login, headless reuse."""

from __future__ import annotations

import asyncio
import os
import re
import secrets
import shutil
import time
from dataclasses import dataclass, field
from urllib.parse import urlparse

from playwright.async_api import (
    Browser,
    BrowserContext,
    Page,
    Playwright,
    Route,
    async_playwright,
)

from .install import launch
from .vault import Vault, VaultError, vault_home

VIEWPORT = {"width": 1280, "height": 900}
# Hides the most obvious automation flag; keeps sites from bouncing the session.
LAUNCH_ARGS = ["--disable-blink-features=AutomationControlled"]

# Tags visible interactive elements with data-as-ref and returns a compact outline.
SNAPSHOT_JS = r"""
(maxItems) => {
  document.querySelectorAll('[data-as-ref]').forEach(e => e.removeAttribute('data-as-ref'));
  const SEL = 'a[href],button,input,select,textarea,summary,[role=button],[role=link],' +
    '[role=checkbox],[role=radio],[role=tab],[role=menuitem],[role=option],[role=switch],' +
    '[role=combobox],[role=textbox],[contenteditable=""],[contenteditable=true],[onclick],' +
    'h1,h2,h3';
  const visible = el => {
    const r = el.getBoundingClientRect();
    if (r.width === 0 || r.height === 0) return false;
    const s = getComputedStyle(el);
    return s.visibility !== 'hidden' && s.display !== 'none' && s.opacity !== '0';
  };
  const clean = s => (s || '').replace(/\s+/g, ' ').trim().slice(0, 80);
  const nameOf = el => {
    const lb = el.getAttribute('aria-labelledby');
    if (lb) { const t = lb.split(' ').map(id => document.getElementById(id)?.innerText).join(' '); if (clean(t)) return clean(t); }
    if (el.getAttribute('aria-label')) return clean(el.getAttribute('aria-label'));
    if (el.id) { const l = document.querySelector(`label[for="${CSS.escape(el.id)}"]`); if (l) return clean(l.innerText); }
    const wrap = el.closest('label'); if (wrap && wrap !== el) return clean(wrap.innerText);
    return clean((el.tagName === 'SELECT' ? '' : el.innerText) || el.getAttribute('placeholder') || el.getAttribute('title') ||
                 el.getAttribute('alt') || el.querySelector?.('img')?.alt || el.getAttribute('name') || '');
  };
  const roleOf = el => {
    const r = el.getAttribute('role'); if (r) return r;
    const t = el.tagName.toLowerCase();
    if (/^h[1-3]$/.test(t)) return 'heading';
    if (t === 'a') return 'link';
    if (t === 'select') return 'combobox';
    if (t === 'textarea') return 'textbox';
    if (t === 'input') {
      const ty = (el.type || 'text').toLowerCase();
      if (['checkbox','radio'].includes(ty)) return ty;
      if (['submit','button','reset','image'].includes(ty)) return 'button';
      return ty === 'text' ? 'textbox' : `textbox:${ty}`;
    }
    if (el.isContentEditable) return 'textbox';
    return t === 'summary' ? 'button' : t;
  };
  const lines = []; let n = 0;
  for (const el of document.querySelectorAll(SEL)) {
    if (n >= maxItems) { lines.push(`... (truncated at ${maxItems} items)`); break; }
    if (!visible(el)) continue;
    const role = roleOf(el); const name = nameOf(el);
    if (role === 'heading') { if (name) lines.push(`# ${name}`); continue; }
    const ref = 'e' + (++n);
    el.setAttribute('data-as-ref', ref);
    let extra = '';
    if (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA') {
      if (el.type === 'password') extra = el.value ? ' value=<hidden>' : '';
      else if (['checkbox','radio'].includes(el.type)) extra = el.checked ? ' [checked]' : '';
      else if (el.value) extra = ` value="${clean(el.value)}"`;
    } else if (el.tagName === 'SELECT') {
      extra = ` selected="${clean(el.options[el.selectedIndex]?.text)}" options=[` +
        [...el.options].slice(0, 15).map(o => clean(o.text)).join('|') + ']';
    }
    if (el.disabled) extra += ' [disabled]';
    if (role === 'link') { const h = el.getAttribute('href'); if (h && !h.startsWith('javascript')) extra += ` -> ${h.slice(0, 100)}`; }
    lines.push(`[${ref}] ${role} "${name}"${extra}`);
  }
  return lines.join('\n');
}
"""


def host_allowed(url: str, allowed: list[str]) -> bool:
    if not allowed:
        return True
    host = (urlparse(url).hostname or "").lower()
    if not host:  # about:blank, data:, etc.
        return True
    return any(host == d or host.endswith("." + d) for d in allowed)


@dataclass
class Session:
    id: str
    profile: str
    context: BrowserContext
    meta: dict
    pages: list[Page] = field(default_factory=list)
    active: Page | None = None
    screenshots: bool = False  # attach a screenshot to every action result
    shot_count: int = 0


@dataclass
class PendingLogin:
    profile: str
    browser: Browser
    context: BrowserContext
    meta: dict
    initial_cookies: int = 0
    cookies: list = field(default_factory=list)
    local_storage: dict[str, list] = field(default_factory=dict)  # origin -> [{name, value}]
    done: asyncio.Event = field(default_factory=asyncio.Event)  # set when the login is finished
    result: str | None = None
    error: str | None = None
    watcher: asyncio.Task | None = None
    finishing: bool = False
    finished: asyncio.Event = field(default_factory=asyncio.Event)

    def state(self) -> dict:
        return {
            "cookies": self.cookies,
            "origins": [{"origin": o, "localStorage": ls} for o, ls in self.local_storage.items() if ls],
        }


class BrowserManager:
    def __init__(self) -> None:
        self.vault = Vault()
        self._pw: Playwright | None = None
        self._headless: Browser | None = None
        self.sessions: dict[str, Session] = {}
        self.logins: dict[str, PendingLogin] = {}
        self._lock = asyncio.Lock()
        self.shots_dir = vault_home() / "screenshots"
        _prune_old(self.shots_dir, days=7)

    async def _playwright(self) -> Playwright:
        if self._pw is None:
            self._pw = await async_playwright().start()
        return self._pw

    async def _headless_browser(self) -> Browser:
        async with self._lock:
            if self._headless is None or not self._headless.is_connected():
                pw = await self._playwright()
                self._headless = await launch(pw, headless=os.environ.get("ASSERTIFY_HEADED") != "1", args=LAUNCH_ARGS)
            return self._headless

    # ---------- login (headed, user-driven) ----------

    async def start_login(self, profile: str, url: str, allowed_domains: list[str]) -> str:
        self.vault._path(profile)  # validates name early
        old = self.logins.get(profile)
        if old and not old.done.is_set() and old.context.pages:
            await old.context.pages[-1].bring_to_front()
            return f"The login window for {profile!r} is already open; I brought it to the front."
        if old:  # finished, or its window was closed: start over
            await self._finish_login(old, save=False)

        pw = await self._playwright()
        browser = await launch(pw, headless=False, args=LAUNCH_ARGS)
        try:
            state, _ = self.vault.load(profile)  # re-login on top of an existing session
        except VaultError:
            state = None
        context = await browser.new_context(viewport=VIEWPORT, storage_state=state)
        page = await context.new_page()
        ua = await page.evaluate("navigator.userAgent")
        domains = allowed_domains or [_base_domain(url)]
        meta = {"start_url": url, "allowed_domains": domains, "user_agent": ua.replace("HeadlessChrome", "Chrome")}
        login = PendingLogin(profile, browser, context, meta, initial_cookies=len(state["cookies"]) if state else 0)
        if state:
            login.local_storage = {o["origin"]: o.get("localStorage", []) for o in state.get("origins", [])}
        self.logins[profile] = login

        # Closing the window (or its last tab) finishes the login instead of leaving it stuck.
        def on_page(p: Page) -> None:
            p.on("close", lambda _: context.pages or login.done.set())

        on_page(page)
        context.on("page", on_page)
        browser.on("disconnected", lambda _: login.done.set())
        login.watcher = asyncio.create_task(self._watch_login(login))
        await page.goto(url)
        return (
            f"A browser window is open at {url}. Log in there (including any 2FA). "
            f"When you're done, close the window or call complete_login('{profile}')."
        )

    async def _backup(self, login: PendingLogin) -> None:
        """Copy cookies + localStorage of open tabs. Unlike storage_state(), this never opens a tab."""
        try:
            login.cookies = await login.context.cookies()
        except Exception:
            return
        for p in list(login.context.pages):
            try:
                origin, items = await p.evaluate(
                    "() => [location.origin, Object.entries(localStorage).map(([name, value]) => ({name, value}))]"
                )
                if origin.startswith("http"):
                    login.local_storage[origin] = items
            except Exception:
                pass

    async def _watch_login(self, login: PendingLogin) -> None:
        while not login.done.is_set():
            await self._backup(login)
            try:
                await asyncio.wait_for(login.done.wait(), timeout=1.5)
            except asyncio.TimeoutError:
                pass
        if not login.finishing:  # user closed the window: save automatically
            await self._finish_login(login, save=True, final_backup=True)

    async def _finish_login(self, login: PendingLogin, save: bool, final_backup: bool = False) -> None:
        if login.finishing:  # closing the window and complete_login can race; save only once
            await login.finished.wait()
            return
        login.finishing = True
        try:
            await self._finish_login_once(login, save, final_backup)
        finally:
            login.finished.set()

    async def _finish_login_once(self, login: PendingLogin, save: bool, final_backup: bool) -> None:
        login.done.set()
        if final_backup and login.browser.is_connected():
            await self._backup(login)  # works even after the last tab closed (macOS keeps the browser alive)
        state = login.state()
        if not save:
            login.error = "cancelled"
        elif not state["cookies"]:
            login.error = "No cookies were captured, so nothing was saved. Run the login again."
        else:
            try:
                _, old_meta = self.vault.load(login.profile)
                login.meta["created_at"] = old_meta.get("created_at")
            except VaultError:
                pass
            self.vault.save(login.profile, state, login.meta)
            login.result = f"Saved encrypted session {login.profile!r} ({len(state['cookies'])} cookies)."
        try:
            await login.browser.close()
        except Exception:
            pass

    async def complete_login(self, profile: str) -> str:
        login = self.logins.pop(profile, None)
        if login is None:
            raise VaultError(f"No login in progress for {profile!r}. Call start_login first.")
        await self._finish_login(login, save=True, final_backup=True)
        if login.watcher:
            login.watcher.cancel()
        if login.error:
            raise VaultError(login.error)
        return login.result

    async def wait_login(self, profile: str) -> str:
        """Block until the user closes the login window; returns the save result."""
        login = self.logins[profile]
        await login.done.wait()
        if login.watcher:
            await asyncio.gather(login.watcher, return_exceptions=True)
        return await self.complete_login(profile)

    async def cancel_login(self, profile: str) -> None:
        login = self.logins.pop(profile, None)
        if login:
            if login.watcher:
                login.watcher.cancel()
            await self._finish_login(login, save=False)

    # ---------- agent sessions (headless) ----------

    async def open_session(self, profile: str) -> Session:
        state, meta = self.vault.load(profile)
        browser = await self._headless_browser()
        context = await browser.new_context(viewport=VIEWPORT, storage_state=state, user_agent=meta.get("user_agent"))
        sid = f"{profile}-{secrets.token_hex(3)}"
        session = Session(sid, profile, context, meta)
        allowed = meta.get("allowed_domains") or []

        async def guard(route: Route) -> None:
            req = route.request
            if req.is_navigation_request() and req.frame.parent_frame is None and not host_allowed(req.url, allowed):
                await route.abort("blockedbyclient")
            else:
                await route.fallback()

        if allowed and os.environ.get("ASSERTIFY_ALLOW_ANY_DOMAIN") != "1":
            await context.route("**/*", guard)

        def on_page(p: Page) -> None:  # popups / target=_blank become the active tab
            session.pages.append(p)
            session.active = p
            p.on("close", lambda _: _on_close(session, p))

        context.on("page", on_page)
        page = await context.new_page()
        await page.goto(meta["start_url"], wait_until="domcontentloaded")
        self.sessions[sid] = session
        return session

    def get(self, sid: str) -> Session:
        s = self.sessions.get(sid)
        if s is None:
            raise VaultError(f"Unknown session {sid!r}. Open one with open_session.")
        if s.active is None or s.active.is_closed():
            raise VaultError("Session has no open tab. Close it and open a new one.")
        return s

    async def save_session(self, sid: str) -> int:
        """Write refreshed cookies/tokens back to the vault."""
        s = self.sessions[sid]
        state = await s.context.storage_state(indexed_db=True)
        self.vault.save(s.profile, state, s.meta)
        return len(state.get("cookies", []))

    async def close_session(self, sid: str, save: bool = True) -> None:
        s = self.sessions.get(sid)
        if s is None:
            return
        try:
            if save:
                await self.save_session(sid)
        finally:
            self.sessions.pop(sid, None)
            await s.context.close()

    async def capture(
        self, sid: str, label: str = "", full_page: bool = False, ref: str | None = None
    ) -> tuple[bytes, str]:
        """Screenshot the active page (or one element) and save it to a private file. Returns (jpeg, path)."""
        s = self.get(sid)
        if ref:
            ref = ref.strip("[]")  # (kept out of the f-string for Python < 3.12)
            target = s.active.locator(f'[data-as-ref="{ref}"]')
            if await target.count() == 0:
                raise VaultError(f"Ref {ref!r} is not on the page anymore. Call snapshot to get fresh refs.")
            data = await target.first.screenshot(type="jpeg", quality=75, timeout=10000)
        else:
            data = await s.active.screenshot(full_page=full_page, type="jpeg", quality=75)
        folder = self.shots_dir / sid
        folder.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self.shots_dir, 0o700)
        s.shot_count += 1
        slug = re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-")[:40] or "page"
        path = folder / f"{s.shot_count:03d}-{slug}.jpg"
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        return data, str(path)

    async def snapshot(self, sid: str, max_items: int = 250) -> str:
        page = self.get(sid).active
        try:
            await page.wait_for_load_state("domcontentloaded", timeout=5000)
        except Exception:
            pass
        outline = await page.evaluate(SNAPSHOT_JS, max_items)
        tabs = len(self.sessions[sid].pages)
        return f"URL: {page.url}\nTitle: {await page.title()}\nTabs: {tabs}\n\n{outline or '(no interactive elements found)'}"

    async def shutdown(self) -> None:
        for sid in list(self.sessions):
            try:
                await self.close_session(sid, save=True)
            except Exception:
                pass
        for name in list(self.logins):
            await self.cancel_login(name)
        if self._headless:
            await self._headless.close()
        if self._pw:
            await self._pw.stop()


def _on_close(session: Session, page: Page) -> None:
    if page in session.pages:
        session.pages.remove(page)
    if session.active is page:
        session.active = session.pages[-1] if session.pages else None


def _base_domain(url: str) -> str:
    """'https://app.example.co.uk/x' -> 'example.co.uk' (rough; good enough for an allowlist default)."""
    host = (urlparse(url).hostname or "").lower()
    parts = host.split(".")
    if len(parts) >= 3 and len(parts[-1]) == 2 and parts[-2] in {"co", "com", "org", "net", "ac", "gov"}:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:]) if len(parts) >= 2 else host


def _prune_old(folder, days: int) -> None:
    """Screenshots can show private data: delete session folders older than `days`."""
    if not folder.exists():
        return
    cutoff = time.time() - days * 86400
    for d in folder.iterdir():
        try:
            if d.stat().st_mtime < cutoff:
                shutil.rmtree(d) if d.is_dir() else d.unlink()
        except OSError:
            pass
