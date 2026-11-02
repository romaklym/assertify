"""Several accounts for one site: email names, site filter, account detection, opening all at once."""

import asyncio
import os
import sys

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from playwright.async_api import async_playwright
from test_e2e import COOKIE, _text, site  # noqa: F401  (site is a fixture)

from assertify.browser import ACCOUNT_JS, NOT_ACCOUNT, BrowserManager
from assertify.vault import Vault, VaultError

GOOGLE = {"site": "google.com", "start_url": "https://mail.google.com/", "allowed_domains": ["google.com"]}


def test_email_names_rename_and_site_filter():
    v = Vault()
    v.save("me@gmail.com", {"cookies": []}, {**GOOGLE, "account": "me@gmail.com"})
    v.save("work+x@gmail.com", {"cookies": []}, {**GOOGLE, "account": "work+x@gmail.com"})
    v.save("linkedin.com-1", {"cookies": []}, {"site": "linkedin.com", "allowed_domains": ["linkedin.com"]})
    assert {p["name"] for p in v.list("google.com")} == {"me@gmail.com", "work+x@gmail.com"}
    assert {p["name"] for p in v.list("mail.google.com")} == {"me@gmail.com", "work+x@gmail.com"}
    assert [p["name"] for p in v.list("linkedin")] == ["linkedin.com-1"]

    v.rename("linkedin.com-1", "linkedin-work")
    assert v.exists("linkedin-work") and not v.exists("linkedin.com-1")
    assert v.load("linkedin-work")[1]["name"] == "linkedin-work"
    with pytest.raises(VaultError, match="already exists"):
        v.rename("linkedin-work", "me@gmail.com")

    m = BrowserManager()
    assert m.resolve("WORK+x@gmail.com") == "work+x@gmail.com"  # by account email
    assert m._final_name("new@gmail.com", "google.com") == "new@gmail.com"
    assert m._final_name(None, "linkedin.com") == "linkedin.com-1"


def test_account_detection():
    page = """<title>Inbox (3) - me@gmail.com - Gmail</title>
    <a aria-label="Google Account: Me (me@gmail.com)">x</a>
    <p>From friend@example.org, noreply@google.com</p><img src="logo@2x.png">"""

    async def run():
        async with async_playwright() as pw:
            b = await pw.chromium.launch()
            p = await b.new_page()
            await p.set_content(page)
            hits = await p.evaluate(ACCOUNT_JS)
            await b.close()
        return hits

    scores: dict[str, float] = {}
    for email, w in asyncio.run(run()):
        if not NOT_ACCOUNT.search(email):
            scores[email] = scores.get(email, 0) + w
    assert max(scores, key=scores.get) == "me@gmail.com"
    assert "noreply@google.com" not in scores and "logo@2x.png" not in scores


async def _open_all(url: str) -> None:
    for email in ["a@example.com", "b@example.com"]:
        Vault().save(
            email,
            {"cookies": [COOKIE], "origins": []},
            {"start_url": url, "site": "127.0.0.1", "allowed_domains": ["127.0.0.1"], "account": email},
        )
    params = StdioServerParameters(command=sys.executable, args=["-m", "assertify", "serve"], env=dict(os.environ))
    async with stdio_client(params) as (r, w), ClientSession(r, w) as s:
        await s.initialize()
        listed = await s.call_tool("list_profiles", {"site": "127.0.0.1"})
        assert "a@example.com" in _text(listed) and "b@example.com" in _text(listed)

        out = _text(await s.call_tool("open_sessions", {"site": "127.0.0.1"}))
        assert "Opened 2 of 2" in out, out
        sids = [ln.split("session_id ")[1].split(" ")[0] for ln in out.splitlines() if ln.startswith("- ")]
        assert len(set(sids)) == 2
        for sid in sids:
            assert "Title: Inbox" in _text(await s.call_tool("snapshot", {"session_id": sid}))
            await s.call_tool("close_session", {"session_id": sid})

        one = _text(await s.call_tool("open_session", {"profile": "b@example.com"}))
        assert one.startswith("session_id: b@example.com-")


def test_open_all_accounts_of_a_site(site):  # noqa: F811
    asyncio.run(asyncio.wait_for(_open_all(site), timeout=90))
