<!-- mcp-name: io.github.romaklym/assertify -->
<div align="center">

<img src="assets/icon.png" width="112" alt="Assertify logo">

# Assertify

**Let your AI agent use any website you're logged in to.**<br>
Log in once. Your session stays encrypted on your machine. Claude, Codex, Cursor and any MCP client can then browse, click, type and read for you.

[![CI](https://github.com/romaklym/assertify/actions/workflows/ci.yml/badge.svg)](https://github.com/romaklym/assertify/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-6366f1.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-3776ab.svg)](https://www.python.org)
[![MCP](https://img.shields.io/badge/MCP-server-000.svg)](https://modelcontextprotocol.io)
[![Playwright](https://img.shields.io/badge/built%20on-Playwright-2EAD33.svg)](https://playwright.dev)

[Quick start](#-quick-start) · [Connect your client](#-connect-your-ai-client) · [Tools](#-tools) · [Security](#-security) · [FAQ](#-faq)

</div>

---

```text
You:    Check my LinkedIn messages and summarize anything from recruiters.
Agent:  open_session("linkedin") → click "Messaging" → read_text …
        You have 3 recruiter messages. The most recent is from Dana at Acme, about a Senior QA role …
```

## ✨ Why Assertify

Most sites have no API, or one that can't do what you need. Assertify gives your agent a real browser that is **already logged in as you**, without ever handing it your password.

- 🔐 **Log in once, by hand.** A normal browser window opens; you sign in (2FA, passkeys, SSO all work). The agent never sees your password.
- 🧳 **Encrypted, local, yours.** Sessions are AES-256-GCM encrypted with a key in your OS keychain. Nothing is uploaded anywhere. There is no server and no account.
- 🤖 **Works with every MCP client.** Claude Code, Claude Desktop, Codex, Cursor, VS Code, Gemini CLI, Grok, Windsurf…
- 👀 **See what the agent sees.** Every step can come with a screenshot, shown in the chat and saved to disk.
- 🛡️ **Fenced in.** Each login is locked to its own domains, so a prompt injection on a page can't walk your logged-in browser somewhere else.
- 👥 **Many accounts per site.** Five Gmail accounts? Log in to each; they're named after their emails. Use one, or open them all at once.
- ✋ **Asks before it acts.** Buttons that send, post, buy, delete or connect are paused until you say yes. Logins can be made read-only.
- 🧍 **Behaves like a person.** Real Chrome, your own browser fingerprint, curved mouse moves, uneven typing and natural pauses. No `navigator.webdriver` flag.
- 🪟 **Handles pop-ups.** Cookie banners are declined for you; "share your contact info" style pop-ups are flagged so the agent decides, or closes them.
- 🔁 **Hands back to you when needed.** CAPTCHAs, 2FA prompts and expired logins open in a window for you to finish; the agent then carries on.
- 🪶 **Fast and token-cheap.** The agent reads a compact outline (`[e12] button "Send"`), not raw HTML.

## ⚙️ How it works

```mermaid
flowchart LR
    U([You]) -- "log in once<br/>(visible window)" --> L[Login browser]
    L -- cookies + storage --> V[(Encrypted vault<br/>~/.assertify-mcp)]
    K[[OS keychain]] -. key .-> V
    A([AI agent]) -- MCP tools --> S[Assertify server]
    V -- decrypt --> S
    S -- drives --> H[Headless browser<br/>already logged in]
    H -- outline + screenshots --> A
```

Everything above runs on your computer.

## 🚀 Quick start

You need [uv](https://docs.astral.sh/uv/getting-started/installation/) (`curl -LsSf https://astral.sh/uv/install.sh | sh`).

```bash
git clone https://github.com/romaklym/assertify.git
cd assertify
uv sync
uv run assertify setup
```

`setup` downloads the browser (Chromium, about 300 MB, once), checks your keychain, and prints the exact command to connect your AI client. If you skip it, Assertify downloads the browser on first use, or falls back to your installed Chrome or Edge.

Then save your first login:

```bash
uv run assertify login github https://github.com/login
```

A browser window opens. Sign in, then close the window (or press Enter in the terminal). Done. Your agent can now use GitHub as you.

> [!TIP]
> You can also just ask your agent: *"log me in to Notion"*. It calls `start_login`, the window opens, and the session saves when you close it.

## 🔌 Connect your AI client

Replace `/path/to/assertify` with where you cloned it (`assertify setup` prints the exact line for you).

<details open>
<summary><b>Claude Code</b></summary>

```bash
claude mcp add -s user assertify -- uv --directory /path/to/assertify run assertify serve
```
</details>

<details>
<summary><b>Claude Desktop</b></summary>

**Easiest:** download [`assertify.mcpb`](https://github.com/romaklym/assertify/releases/latest/download/assertify.mcpb) and double-click it. Claude Desktop installs it with its icon and handles Python for you.

Or add it to `claude_desktop_config.json` by hand:

```json
{
  "mcpServers": {
    "assertify": {
      "command": "uv",
      "args": ["--directory", "/path/to/assertify", "run", "assertify", "serve"]
    }
  }
}
```
</details>

<details>
<summary><b>Codex</b></summary>

```bash
codex mcp add assertify -- uv --directory /path/to/assertify run assertify serve
```

or in `~/.codex/config.toml`:

```toml
[mcp_servers.assertify]
command = "uv"
args = ["--directory", "/path/to/assertify", "run", "assertify", "serve"]
```
</details>

<details>
<summary><b>Cursor</b></summary>

`~/.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "assertify": {
      "command": "uv",
      "args": ["--directory", "/path/to/assertify", "run", "assertify", "serve"]
    }
  }
}
```
</details>

<details>
<summary><b>VS Code (Copilot)</b></summary>

`.vscode/mcp.json`:

```json
{
  "servers": {
    "assertify": {
      "type": "stdio",
      "command": "uv",
      "args": ["--directory", "/path/to/assertify", "run", "assertify", "serve"]
    }
  }
}
```
</details>

<details>
<summary><b>Gemini CLI, Grok, Windsurf, Zed and others</b></summary>

Any client that runs local (stdio) MCP servers works. Use this command:

```text
uv --directory /path/to/assertify run assertify serve
```

For JSON configs, use the `mcpServers` block shown under Cursor.
</details>

## 🧰 Tools

| Tool | What it does |
|---|---|
| `list_profiles(site?)` | Your saved logins (name, account email, site), optionally only one site's |
| `start_login(url, profile?)` / `complete_login` | Open a window for **you** to log in, then encrypt and save the session. No name: it's named after the account's email |
| `rename_profile` · `delete_profile` | Rename or remove a saved login |
| `open_session(profile, url?, screenshots?)` | Start a logged-in headless browser; returns a `session_id` and a page outline |
| `open_sessions(site? \| profiles?)` | Open several logins at once (e.g. every Gmail account), one `session_id` each |
| `snapshot` | URL, title and interactive elements as `[e12] button "Save"`; pop-ups first, warnings for CAPTCHAs and sign-in pages |
| `find(query)` | Search the whole page for elements by label |
| `click` · `type_text` · `select_option` · `press_key` · `scroll` · `back` · `navigate` · `wait_for` | Act by ref **or by visible text** (`click(text="Messages")`), so small redesigns don't break a flow; each returns a fresh outline |
| `dismiss_popup` | Close the pop-up on top with its close / "Not now" button |
| `handoff(reason?)` | Open the current page in a window for **you** (CAPTCHA, 2FA, expired login); the session picks up your fresh login |
| `read_text` | The visible text of the page, marked as untrusted website content |
| `screenshot(ref?, full_page?)` | Screenshot of the page or one element, shown to the agent and saved to a file |
| `set_screenshots(enabled)` | Attach a screenshot to every step (great for watching a run) |
| `switch_tab` | Popups become the active tab automatically; this switches back |
| `save_session` / `close_session` | Write refreshed cookies back to the vault (closing saves by default) |
| `evaluate` | Run JavaScript in the page. **Off** unless `ASSERTIFY_ALLOW_EVAL=1` |

### 👀 Seeing what the agent sees

Ask *"show me a screenshot"* or *"open my GitHub session with screenshots on so I can follow along"*. Images appear in the chat in clients that show them, and every one is saved to `~/.assertify-mcp/screenshots/<session>/NNN-<step>.jpg`. The folder is private to you and cleared after 7 days.

## 👥 Several accounts on one site

Log in once per account. Leave the name out and Assertify names each login after the email address it finds on the page (falls back to `google.com-1`, `google.com-2`… when a site doesn't show one):

```bash
assertify login https://mail.google.com   # sign in as you@gmail.com   -> saved as "you@gmail.com"
assertify login https://mail.google.com   # sign in as work@gmail.com  -> saved as "work@gmail.com"
assertify login work https://mail.google.com   # or pick the name yourself
assertify list google.com                 # just the Google logins
assertify rename google.com-1 side-project
```

Then just ask:

- *"Check my work@gmail.com inbox"*: the agent opens that one login.
- *"Any unread mail in any of my Gmail accounts?"*: the agent calls `open_sessions(site="google.com")` and gets one session per account, which it can work through side by side.

Each account lives in its own encrypted file and its own isolated browser, so cookies never mix. On sites that restrict automation, avoid running the same action on many accounts at once.

## 🧍 Staying unnoticed

Sites flag browsers that act like robots. Assertify tries hard not to:

- **Real Chrome** when it's installed (falls back to Chromium), without the "controlled by automated software" flag or `navigator.webdriver`.
- **Your fingerprint.** The user agent, language and time zone from your login window are reused by the agent's browser, so the site keeps seeing the same "device".
- **Human input.** The mouse travels along a curve to a random spot inside each button, keys are typed one by one at uneven speed, scrolling comes in flicks, and there are short random pauses between actions and between page loads.
- **A speed limit.** Page loads per login per hour are capped (400 by default, 60 on sites that ban automation).

Set `ASSERTIFY_HUMANIZE=0` to turn the human input off (faster; fine for your own tools and test sites).

## 🪟 Pop-ups, dialogs and expired logins

- **Cookie banners** are answered with "Reject all" / "Only necessary" automatically (`ASSERTIFY_AUTO_CONSENT=0` to turn off).
- **Other pop-ups** (newsletter, "share your contact info", app promos) are listed first in the snapshot under `## Pop-up` with a warning. The agent decides based on your request, or calls `dismiss_popup`. A click on something hidden behind a pop-up is refused with a hint instead of silently hitting the overlay.
- **Browser dialogs** (`alert`, `confirm`, "Are you sure?") are cancelled and reported; the agent repeats the click with `accept_dialog=true` when it means it.
- **CAPTCHAs, 2FA and expired sessions** show a warning in the snapshot. The agent never tries to solve them: it calls `handoff`, a window opens on your screen at the same page, you finish, close it, and the agent continues with the new cookies.

## ⚖️ Use it responsibly

Many sites' terms forbid automated access. LinkedIn, Facebook, Instagram, Threads, X and TikTok say so explicitly and do restrict accounts for it. Assertify recognises these sites, runs slower on them, caps page loads lower and tells the agent to keep tasks small and personal. Light personal use (checking your own messages, updating your own profile) is usually fine; scraping, bulk messaging or mass connecting is how accounts get restricted. You are responsible for following the terms of the sites you use.

## 🔒 Security

- **Storage:** `~/.assertify-mcp/profiles/<name>.enc`, AES-256-GCM, file mode `0600`, folder `0700`. The profile name is bound into the ciphertext, so files can't be swapped or renamed.
- **Key:** a random 256-bit key in your OS keychain (macOS Keychain, Windows Credential Locker, Linux Secret Service). On machines without one, set `ASSERTIFY_PASSPHRASE` to derive the key with scrypt instead.
- **Domain guard:** navigation outside a login's `allowed_domains` is blocked. By default that's the login URL's domain and its subdomains; add more with `--domain` (e.g. for SSO).
- **No passwords in context:** password fields show as `value=<hidden>` in snapshots.
- **No telemetry, no server, no account.** Nothing leaves your machine except your own browser traffic to the sites you use.
- **Ask before acting:** buttons labelled send, post, buy, pay, delete, connect, follow, apply and similar, and pressing Enter in a message box, are paused until the agent calls again with `confirmed=true`, which it is told to do only after you approve.
- **Read-only logins:** `assertify login <name> <url> --read-only` (or `read_only=true` in `start_login`) lets agents browse and read but never type, submit, send or buy.
- **Untrusted pages:** page text is returned wrapped and labelled as website content, and agents are told never to follow instructions found in pages, emails or messages. Only `http(s)` pages can be opened, and downloads are disabled.

> [!WARNING]
> A saved session is as powerful as being logged in. Anyone who can run code as your user while your keychain is unlocked can use it, the same as your browser's own cookies. Only connect agents you trust.

Found a vulnerability? See [SECURITY.md](SECURITY.md).

## 🎛️ Configuration

| Variable | Effect |
|---|---|
| `ASSERTIFY_HOME` | Vault location (default `~/.assertify-mcp`) |
| `ASSERTIFY_PASSPHRASE` | Use a passphrase instead of the OS keychain |
| `ASSERTIFY_HEADED=1` | Show the agent's browser window (debugging, or sites that block headless) |
| `ASSERTIFY_SCREENSHOTS=1` | Screenshot every step by default |
| `ASSERTIFY_NO_AUTO_INSTALL=1` | Never download Chromium automatically |
| `ASSERTIFY_ALLOW_EVAL=1` | Enable the `evaluate` tool |
| `ASSERTIFY_ALLOW_ANY_DOMAIN=1` | Turn off the domain guard |
| `ASSERTIFY_HUMANIZE=0` | Turn off human-like mouse, typing and pauses |
| `ASSERTIFY_BROWSER` | `chrome`, `chromium` or `msedge` (default: Chrome if installed, else Chromium) |
| `ASSERTIFY_MAX_PAGES_PER_HOUR` | Page-load cap per login (default 400; 60 on strict sites) |
| `ASSERTIFY_AUTO_CONSENT=0` | Don't auto-decline cookie banners |

CLI: `assertify setup | login [name] <url> [--domain d] [--read-only] | list [site] | rename <name> <new> | delete <name> | serve`.

## ❓ FAQ

**Does it work with 2FA, passkeys and "Sign in with Google"?**
Yes. You log in yourself in a real browser window, so anything you can do there works. Add the SSO domain with `--domain` if the site bounces through one.

**Why did a site log me out?**
Sessions expire on the site's own schedule, and some sites ask for a CAPTCHA or 2FA again now and then. When that happens the agent calls `handoff` and a window opens for you to sign in again; nothing else to do. Assertify also saves refreshed cookies when a session closes, which keeps rolling sessions alive. If a site keeps rejecting the headless browser, set `ASSERTIFY_HEADED=1`.

**Will a site redesign break my agent?**
Less than you'd think. The agent reads the page fresh every step and can click by visible text (`click(text="Messages")`) instead of fixed selectors, so it adapts like a person would. A full redesign can still confuse it; it will tell you what it sees.

**Can I use it from my phone or a server?**
Not yet. Assertify is local-first by design: your sessions never leave your computer.

**Known limits**
Login saves cookies and localStorage, not IndexedDB, so a few apps that keep their token only in IndexedDB won't stay logged in. No anti-detection is perfect: a site determined to spot automation may still do so. Snapshots don't look inside iframes or closed shadow roots yet.

## 🤝 Contributing

Issues and PRs are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md). The short version:

```bash
uv sync && uv run assertify setup
uv run pytest && uv run ruff check .
```

## 📄 License

[MIT](LICENSE) © Roman Klym
