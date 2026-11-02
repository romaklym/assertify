"""MCP server exposing saved-login browser sessions as tools."""

from __future__ import annotations

import base64
import functools
import os
from contextlib import asynccontextmanager
from pathlib import Path

from mcp.server.mcpserver import Image, MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import Icon, ToolAnnotations

from . import __version__
from .browser import BrowserManager

REPO_URL = "https://github.com/romaklym/assertify-mcp"
_ICON = base64.b64encode((Path(__file__).parent / "icon.png").read_bytes()).decode()

manager = BrowserManager()


@asynccontextmanager
async def lifespan(_server):
    try:
        yield
    finally:
        await manager.shutdown()  # saves open sessions so refreshed tokens aren't lost


mcp = MCPServer(
    "assertify",
    title="Assertify",
    version=__version__,
    website_url=REPO_URL,
    icons=[Icon(src=f"data:image/png;base64,{_ICON}", mime_type="image/png", sizes=["128x128"])],
    lifespan=lifespan,
    instructions=(
        "Use websites through the user's saved logins. Flow: list_profiles -> open_session -> "
        "snapshot -> click/type_text/... using [eN] refs from the latest snapshot -> close_session. "
        "Refs change after every snapshot; take a new snapshot after any action that changes the page. "
        "If a profile is missing or logged out, ask the user to log in with start_login/complete_login. "
        "Ask the user before irreversible actions (purchases, sending messages, deleting data). "
        "When the user wants to see the page, call screenshot and give them the saved file path; "
        "if they want to watch the whole run, open the session with screenshots=True."
    ),
)


def tool(fn=None, *, read_only: bool = False, destructive: bool | None = None):
    """Register a tool; turn any failure into a readable error the agent can act on.

    The hints tell clients which tools only look (safe to auto-approve) and which can delete things.
    """

    def register(fn):
        @functools.wraps(fn)
        async def wrapper(*args, **kwargs):
            try:
                return await fn(*args, **kwargs)
            except ToolError:
                raise
            except Exception as e:
                msg = str(e).split("\nCall log:")[0].strip()  # drop Playwright's verbose call log
                raise ToolError(msg or type(e).__name__) from e

        hints = ToolAnnotations(
            read_only_hint=read_only,
            destructive_hint=False if read_only else destructive,
            open_world_hint=True,
        )
        return mcp.tool(annotations=hints)(wrapper)

    return register(fn) if fn else register


async def _loc(sid: str, ref: str):
    ref = ref.strip("[]")
    loc = manager.get(sid).active.locator(f'[data-as-ref="{ref}"]')
    if await loc.count() == 0:
        raise ToolError(f"Ref {ref!r} is not on the page anymore. Call snapshot to get fresh refs.")
    return loc


Result = list  # text, plus a screenshot when the session has screenshots on


async def _after(sid: str, note: str) -> Result:
    page = manager.get(sid).active
    try:
        await page.wait_for_load_state("domcontentloaded", timeout=5000)
    except Exception:
        pass
    if page.url.startswith("chrome-error://"):  # navigation was blocked by the domain guard
        await page.go_back(wait_until="domcontentloaded")
        note += " -> that navigation was blocked (outside this profile's allowed domains)"
    text = f"{note}\n\n" + await manager.snapshot(sid)
    if not manager.sessions[sid].screenshots:
        return [text]
    data, path = await manager.capture(sid, label=note)
    return [text + f"\n\nScreenshot: {path}", Image(data=data, format="jpeg")]


# ---------- profiles / login ----------


@tool(read_only=True)
async def list_profiles() -> list[dict]:
    """List saved website logins (name, start URL, allowed domains, last updated)."""
    return manager.vault.list()


@tool
async def start_login(profile: str, url: str, allowed_domains: list[str] | None = None) -> str:
    """Open a visible browser window so the USER can log in to a site by hand.

    profile: short name to save it under, e.g. "github".
    url: the site's login page or home page.
    allowed_domains: domains agents may navigate to with this session
      (defaults to the url's base domain, e.g. ["github.com"]).
    The agent never sees the password. Call complete_login once the user says they're done.
    """
    return await manager.start_login(profile, url, allowed_domains or [])


@tool
async def complete_login(profile: str) -> str:
    """Save the logged-in session from the login window (encrypted) and close the window."""
    return await manager.complete_login(profile)


@tool(destructive=True)
async def delete_profile(profile: str) -> str:
    """Delete a saved login from disk."""
    return "Deleted." if manager.vault.delete(profile) else "No such profile."


# ---------- sessions ----------


@tool
async def open_session(profile: str, url: str | None = None, screenshots: bool | None = None) -> Result:
    """Open a headless browser already logged in as the saved profile. Returns a session id and page snapshot.

    screenshots: attach a screenshot to every action's result so the user can follow along
      (default: off, or on when ASSERTIFY_SCREENSHOTS=1). Turn it on when the user wants to watch.
    """
    s = await manager.open_session(profile)
    s.screenshots = screenshots if screenshots is not None else os.environ.get("ASSERTIFY_SCREENSHOTS") == "1"
    if url:
        await s.active.goto(url, wait_until="domcontentloaded")
    return await _after(s.id, f"session_id: {s.id}")


@tool
async def close_session(session_id: str, save: bool = True) -> str:
    """Close a session. With save=True (default), refreshed cookies are written back to the vault."""
    await manager.close_session(session_id, save=save)
    return "Closed."


@tool
async def save_session(session_id: str) -> str:
    """Write the session's current cookies/storage back to the encrypted vault."""
    n = await manager.save_session(session_id)
    return f"Saved ({n} cookies)."


# ---------- page interaction ----------


@tool(read_only=True)
async def snapshot(session_id: str) -> str:
    """Current URL, title and a list of interactive elements with [eN] refs to use in other tools."""
    return await manager.snapshot(session_id)


@tool
async def navigate(session_id: str, url: str) -> Result:
    """Go to a URL (must be within the profile's allowed domains)."""
    page = manager.get(session_id).active
    try:
        await page.goto(url, wait_until="domcontentloaded")
    except Exception as e:
        if "ERR_BLOCKED_BY_CLIENT" in str(e):
            return [f"Blocked: {url} is outside this profile's allowed domains."]
        raise
    return await _after(session_id, f"Navigated to {url}")


@tool
async def back(session_id: str) -> Result:
    """Browser back button."""
    await manager.get(session_id).active.go_back(wait_until="domcontentloaded")
    return await _after(session_id, "Went back")


@tool
async def click(session_id: str, ref: str) -> Result:
    """Click the element with the given ref (e.g. "e12") from the latest snapshot."""
    await (await _loc(session_id, ref)).click(timeout=10000)
    return await _after(session_id, f"Clicked {ref}")


@tool
async def type_text(session_id: str, ref: str, text: str, submit: bool = False) -> Result:
    """Replace the contents of a text field with `text`. submit=True presses Enter afterwards."""
    loc = await _loc(session_id, ref)
    await loc.fill(text, timeout=10000)
    if submit:
        await loc.press("Enter")
    return await _after(session_id, f"Typed into {ref}")


@tool
async def select_option(session_id: str, ref: str, option: str) -> Result:
    """Choose an option (by visible label or value) in a <select> element."""
    loc = await _loc(session_id, ref)
    try:
        await loc.select_option(label=option, timeout=5000)
    except Exception:
        await loc.select_option(value=option, timeout=5000)
    return await _after(session_id, f"Selected {option!r} in {ref}")


@tool
async def press_key(session_id: str, key: str) -> Result:
    """Press a key on the page, e.g. "Enter", "Escape", "Tab", "Control+A"."""
    await manager.get(session_id).active.keyboard.press(key)
    return await _after(session_id, f"Pressed {key}")


@tool
async def scroll(session_id: str, direction: str = "down", amount: int = 800) -> Result:
    """Scroll the page "up" or "down" by `amount` pixels (lazy-loaded content appears in the next snapshot)."""
    page = manager.get(session_id).active
    await page.mouse.wheel(0, amount if direction == "down" else -amount)
    await page.wait_for_timeout(600)
    return await _after(session_id, f"Scrolled {direction}")


@tool
async def wait_for(session_id: str, text: str | None = None, seconds: float = 2) -> Result:
    """Wait until `text` appears on the page (up to 15s), or just wait `seconds`."""
    page = manager.get(session_id).active
    if text:
        await page.get_by_text(text).first.wait_for(timeout=15000)
    else:
        await page.wait_for_timeout(min(seconds, 30) * 1000)
    return await _after(session_id, "Done waiting")


@tool(read_only=True)
async def read_text(session_id: str, max_chars: int = 20000) -> str:
    """Return the visible text of the page (for reading content, tables, messages, etc.)."""
    page = manager.get(session_id).active
    text = await page.evaluate("document.body.innerText")
    return text[:max_chars] + ("\n...(truncated)" if len(text) > max_chars else "")


@tool(read_only=True)
async def screenshot(session_id: str, ref: str | None = None, full_page: bool = False) -> Result:
    """Screenshot the current page, or just one element (ref from the latest snapshot).

    The image is returned to you AND saved to a file whose path is included; when the user wants
    to see something, show them that path.
    """
    page = manager.get(session_id).active
    data, path = await manager.capture(session_id, label=ref or await page.title(), full_page=full_page, ref=ref)
    return [Image(data=data, format="jpeg"), f"Screenshot of {page.url}\nSaved to: {path}"]


@tool
async def set_screenshots(session_id: str, enabled: bool) -> str:
    """Turn per-step screenshots on or off for a session (each action then returns a screenshot)."""
    manager.get(session_id).screenshots = enabled
    return f"Per-step screenshots {'on' if enabled else 'off'}."


@tool
async def switch_tab(session_id: str, index: int) -> Result:
    """Make tab `index` (0-based) the active tab. New tabs/popups become active automatically."""
    s = manager.get(session_id)
    s.active = s.pages[index]
    await s.active.bring_to_front()
    return await _after(session_id, f"Switched to tab {index}")


if os.environ.get("ASSERTIFY_ALLOW_EVAL") == "1":

    @tool
    async def evaluate(session_id: str, script: str) -> str:
        """Run a JavaScript expression in the page and return the result as text."""
        return repr(await manager.get(session_id).active.evaluate(script))


def run() -> None:
    mcp.run()
