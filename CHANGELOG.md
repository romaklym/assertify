# Changelog

## Unreleased

- Windows: pressing Enter now finishes `assertify login` (it used to wait for the window to close), and the CLI no longer crashes on consoles that aren't UTF-8.
- macOS/Windows: renaming a profile when only the letter case changes (`Work` → `work`) no longer deletes it.
- Linux: a clear message when there's no screen for the login window.
- CI now tests Windows too. README diagram shows multiple accounts.

## 0.3.0 (2026-11-02)

- Several accounts per site: log in without a name and the login is named after the account's email; `list_profiles(site)` / `assertify list <site>`; new `open_sessions` opens every account of a site (or a list) at once; `open_session` also accepts the account email; new `rename_profile` / `assertify rename`.
- Profile names may contain `@` and `+`, so an email works as a name.

## 0.2.0 (2026-11-02)

Hardening: harder to detect, safer with your accounts, better with pop-ups and expired logins.

- Human-like input: curved mouse moves to random points, per-key typing, uneven scrolling, random pauses (`ASSERTIFY_HUMANIZE=0` to turn off).
- Stealth: real Chrome first, no automation flag or `navigator.webdriver`, the login window's user agent, language and time zone reused by the agent.
- Pop-ups: listed first in snapshots with a warning; new `dismiss_popup`; clicks behind a pop-up are refused with a hint; cookie banners declined automatically; `alert`/`confirm` boxes reported and cancelled unless `accept_dialog=true`.
- Safety: send/buy/delete/connect-style buttons and Enter in message boxes need `confirmed=true`; read-only logins (`--read-only`); page text labelled as untrusted; only http(s) URLs; downloads disabled.
- Terms of service: LinkedIn, Facebook, Instagram, Threads, X and TikTok get slower pacing and a lower page-load cap; hourly cap for all sites (`ASSERTIFY_MAX_PAGES_PER_HOUR`).
- Expired sessions: snapshots flag CAPTCHAs and sign-in pages; new `handoff` opens the page for you and refreshes the agent's session afterwards.
- Redesign-proofing: `click`, `type_text` and `select_option` accept visible text instead of a ref; new `find` searches the whole page.
- Fix: a blocked navigation no longer leaves the session on Chrome's error page.

## 0.1.0 (2026-11-02)

First public release.

- Log in once in a visible browser; the session is saved encrypted (AES-256-GCM, OS keychain key).
- Headless, logged-in browser sessions for agents: snapshot, click, type, select, scroll, navigate, read, tabs.
- Screenshots shown to the agent and saved locally; optional screenshot on every step.
- Per-login domain guard.
- `assertify setup` installs the browser; automatic download or Chrome/Edge fallback on first use.
- Claude Desktop extension (`.mcpb`) and MCP Registry listing.
