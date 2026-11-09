# Changelog

## 0.7.0 (2026-11-09)

- Assertify Cloud: a public MCP server at `https://mcp.assertify.co/mcp` with OAuth sign-in (dynamic client registration and PKCE). It relays tool calls to the new `assertify connect` companion on your computer over one outbound WebSocket, so claude.ai, ChatGPT, Codex and the plugin directories can use Assertify while the browser and logins stay on your computer. `assertify link CODE` approves an app from its sign-in page, `assertify unlink` revokes them all, and `assertify cloud` runs the server (see `deploy/README.md`).
- The Claude and Codex plugin now connects to `https://mcp.assertify.co/mcp` instead of starting a local server, and ships only Markdown, JSON and images. It also has portable `plugin.json` and `mcp.json` manifests.
- Removed the unfinished phone app (`mobile/`) and `assertify relay`. To use Assertify from Claude or ChatGPT on a phone, add the hosted connector; the browser runs on your computer.
- Tool hints are now exact: `click`, `type_text`, `press_key` and `delete_profile` are marked destructive, `scroll` and `wait_for` read-only, and profile tools as not reaching the web.

## 0.6.3 (2026-11-07)

- Claude plugin: Assertify can be installed with `/plugin install assertify --marketplace romaklym/assertify` and is ready to submit to the Claude plugin directory. It bundles the MCP server and a `use-websites` skill.
- Published on PyPI as `assertify-mcp`, so `uvx assertify-mcp` runs the server. New `assertify-mcp` command, the same as `assertify`.

## 0.6.2 (2026-11-06)

- Fixed downloading Discord images and other attachments that open in a viewer: `download` with the link's ref now fetches the file the link points to instead of clicking it and waiting.
- Long links in snapshots end with `…` when shortened, and `download(url=...)` accepts that shortened link and uses the page's full signed link.

## 0.6.1 (2026-11-06)

- Downloads from files on another host now work (Discord attachments on `cdn.discordapp.com`, files on S3 or Google's content servers). Clicking such a link fetches the file directly instead of timing out, and `download(url=...)` accepts a file outside the login's domains when the page links to it, using the page's own signed link. Other off-site URLs are still refused, and off-site web pages aren't saved.
- Fixed: a link that opens a new tab to a blocked domain no longer hangs the tab.

## 0.6.0 (2026-11-06)

- Sign in with Google (and other providers that block automated browsers): `start_login` now opens your installed Chrome as a normal window with a throwaway profile, instead of an automated one. Assertify only reads its cookies while you sign in, reads the pages once when you're done, then closes it and deletes the profile. Set `ASSERTIFY_LOGIN_WINDOW=playwright` for the old window; `ASSERTIFY_CHROME_PATH` picks the browser.
- Frames and iframes: snapshots, clicks, typing and `read_text` now reach inside them (old framed dashboards, embedded editors like TinyMCE, report viewers). Ad and CAPTCHA frames are left out.
- Shadow DOM: buttons and fields inside web components now show up and can be clicked.
- Repeated buttons in tables ("edit", "delete", "View") show which row they belong to, e.g. `row="Smith"`.
- Icon-only buttons and links get a name from their icon's title or label, or else a readable element id.
- Dropdowns no longer show their internal value as the label.
- New `dialog_text` on `click`: answers a browser prompt box.
- `complete_login` warns when the login window is still on a sign-in page (the login probably hadn't finished).
- New `download` tool: saves exports, reports and invoices from a site and reads them back, CSV/TSV and Excel as tables, PDFs and text files as text. Click a download button, fetch a link with the login, or save the file the page just started.
- New `browser_settings` tool for intranets, routers and old admin pages: you type the password for the browser's own sign-in box (HTTP Basic/NTLM) in a small window and can trust a self-signed certificate. The agent never sees the password; it's stored encrypted and sent only to that site. Agents get a hint to use it when a site asks for one or its certificate isn't trusted.
- Logins that live outside cookies now stick: the login window saves sessionStorage and IndexedDB as well as localStorage (WhatsApp Web, Teams and similar web apps), and agent sessions save and restore sessionStorage.
- The native Chrome login window now also saves a site's storage when you just close the window, reading it only from tabs that aren't sign-in pages.
- IndexedDB values that aren't plain JSON now carry over: dates, binary data, files and Blobs, Maps and Sets, big integers and exportable encryption keys. Assertify writes the databases back itself before the agent's first visit, and saving an agent session no longer turns files and keys into empty objects (Playwright's own save did). A database it can't copy (an encryption key the browser locks, or over 25 MB) is kept from the earlier save if there is one, and named in the save message and in `list_profiles` (`storage_not_copied`).
- When the user logs in again during a session, open tabs now also get the new sessionStorage and IndexedDB, not only cookies and localStorage.
- Sites that hide their storage from page scripts (Discord deletes `window.localStorage`) now save their login: storage is read in an isolated script world the page can't touch, every ~5 seconds while the window is open. A read that fails no longer wipes what was already captured, logins kept only in storage (no cookies) are saved, and `list_profiles` and save messages show storage counts next to cookies.
- Clearer empty snapshots: says when a page is still loading or failed to load its scripts, or is made only of frames. Page text no longer carries runs of blank lines.

## 0.5.0 (2026-11-05)

- Phones: a Flutter app for iPhone and Android (`mobile/`). Log in to any site in the app's browser; agents then work in a hidden browser on the phone with your login.
- New `assertify relay`: an MCP server for Claude mobile, ChatGPT/Codex and other remote agents that forwards to the paired phone over a WebSocket. Token-protected, one phone at a time.
- Block, unblock, report and mute buttons now need `confirmed=true` too.

## 0.4.0 (2026-11-02)

- New `upload_files` tool: attach files or whole folders (photos for a post, a PDF for an email). Uses the site's file dialog like a person, else its upload field, else drag-and-drop. Respects single-file fields and file-type limits.
- Uploads never include secrets: hidden folders, keys, certificates, `.env`, cookie stores and the vault are refused. Optional `ASSERTIFY_UPLOAD_DIRS` allowlist and `ASSERTIFY_MAX_UPLOAD_MB` cap.
- Snapshots mention upload fields on the page, and show visible ones as `file-upload`.

## 0.3.1 (2026-11-02)

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
