"""Guards that keep a logged-in session from doing damage.

- Risky clicks (send, buy, delete, ...) need an explicit confirmed=True after asking the user.
- Read-only profiles can browse and read but never type, submit or press risky buttons.
- Sites known to ban automation get slower pacing and a lower page-load budget.
- Only http(s) pages can be opened (no file://, chrome://, data:).
"""

from __future__ import annotations

import os
import re
import time
from collections import deque
from urllib.parse import urlparse

# Button labels that usually commit something the user may not want.
RISKY = re.compile(
    r"\b(send|post|publish|tweet|reply|comment|share|repost|submit|buy|purchase|order|checkout|check out|"
    r"pay|donate|subscribe|unsubscribe|delete|remove|discard|archive|transfer|withdraw|confirm|accept|"
    r"approve|agree|sign|apply|connect|follow|unfollow|invite|endorse|recommend|book|reserve|deactivate|"
    r"close account|cancel (subscription|order|membership|account))\b",
    re.I,
)
SEARCH = re.compile(r"search|find|filter|query|lookup", re.I)
SAFE_KEYS = re.compile(r"^(Escape|Tab|Shift\+Tab|Arrow(Up|Down|Left|Right)|Page(Up|Down)|Home|End)$")

# Sites whose terms forbid automated access and that restrict accounts for it.
STRICT_SITES = {
    "linkedin.com": "LinkedIn",
    "facebook.com": "Facebook",
    "instagram.com": "Instagram",
    "threads.net": "Threads",
    "x.com": "X",
    "twitter.com": "X",
    "tiktok.com": "TikTok",
}


class Blocked(Exception):
    """An action was stopped on purpose; the message tells the agent what to do instead."""


def risky_label(name: str) -> bool:
    return bool(name) and len(name) <= 40 and bool(RISKY.search(name))


def strict_site(domains: list[str]) -> str | None:
    for d in domains:
        for site, label in STRICT_SITES.items():
            if d == site or d.endswith("." + site):
                return label
    return None


def check_url(url: str) -> None:
    scheme = urlparse(url).scheme.lower()
    if scheme not in ("http", "https"):
        raise Blocked(f"Blocked: only http(s) pages can be opened, not {scheme or 'this'}: URLs.")


def check_click(role: str, name: str, submit: bool, read_only: bool, confirmed: bool) -> None:
    if read_only and (submit or risky_label(name)):
        raise Blocked(
            f'Blocked: this profile is read-only, so "{name or role}" can\'t be pressed. '
            "The user can allow it by logging in again without --read-only."
        )
    if risky_label(name) and not confirmed:
        raise Blocked(
            f'Paused: "{name}" may send, buy, delete or publish something. Confirm with the user first, '
            "then call again with confirmed=true."
        )


def check_typing(read_only: bool) -> None:
    if read_only:
        raise Blocked("Blocked: this profile is read-only, so it can't type or change form fields.")


def check_submit(field_name: str, read_only: bool, confirmed: bool) -> None:
    if SEARCH.search(field_name or ""):
        return
    if read_only:
        raise Blocked("Blocked: this profile is read-only, so it can't submit forms or send messages.")
    if not confirmed:
        raise Blocked(
            "Paused: pressing Enter here may send or submit something. Confirm with the user first, "
            "then call again with confirmed=true."
        )


def check_key(key: str, composing: bool, read_only: bool, confirmed: bool) -> None:
    if SAFE_KEYS.match(key):
        return
    if read_only:
        raise Blocked(f"Blocked: this profile is read-only, so it can only press navigation keys, not {key}.")
    if composing and key.split("+")[-1] == "Enter" and not confirmed:
        raise Blocked(
            "Paused: Enter in a message box usually sends the message. Confirm with the user first, "
            "then call again with confirmed=true."
        )


class PageBudget:
    """Caps page loads per profile per hour, so a runaway agent can't hammer a site."""

    def __init__(self) -> None:
        self.loads: dict[str, deque] = {}

    @staticmethod
    def limit(strict: bool) -> int:
        env = os.environ.get("ASSERTIFY_MAX_PAGES_PER_HOUR")
        if env and env.isdigit():
            return int(env)
        return 60 if strict else 400

    def record(self, profile: str) -> None:
        self.loads.setdefault(profile, deque()).append(time.time())

    def check(self, profile: str, site: str | None) -> None:
        q = self.loads.setdefault(profile, deque())
        while q and q[0] < time.time() - 3600:
            q.popleft()
        limit = self.limit(site is not None)
        if len(q) >= limit:
            who = f"your {site} account" if site else "this account"
            raise Blocked(
                f"Paused to protect {who}: {len(q)} page loads in the last hour (limit {limit}). "
                "Wait a while, or raise ASSERTIFY_MAX_PAGES_PER_HOUR."
            )
