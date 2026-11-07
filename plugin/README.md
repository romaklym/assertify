# Assertify plugin

Assertify lets Claude use websites you're logged in to. You sign in once in a real browser window,
the session is saved encrypted on your computer, and Claude can then open that site as you: read
pages, click, type, fill in forms, download files and take screenshots. Actions that send, post,
buy, delete or connect are paused until you approve them.

The plugin contains:

- **An MCP server** (`assertify`) that runs locally on your computer.
- **A skill** (`use-websites`) that teaches Claude the login → browse → close flow and the safety rules.

It works in Claude Code, Cowork and Codex running on your computer. It doesn't load in claude.ai chat,
because the server has to run on your machine. Claude Desktop chat users can install the `.mcpb`
bundle from the [releases page](https://github.com/romaklym/assertify/releases/latest) instead.

## Install

In Claude Code:

```
/plugin marketplace add romaklym/assertify
/plugin install assertify@assertify
```

In Codex:

```
codex plugin marketplace add romaklym/assertify
codex plugin add assertify@assertify
```

## Requirements

- [uv](https://docs.astral.sh/uv/getting-started/installation/)
- Python 3.10 or newer. If you don't have it, uv downloads it for you the first time.
- macOS, Windows or Linux

## What it runs, stores and sends

Everything is listed here so you know exactly what the plugin does on your computer.

- **What runs:** the plugin starts `uvx assertify-mcp==0.6.3`. uv downloads that exact version of
  the open-source [`assertify-mcp`](https://pypi.org/project/assertify-mcp/) package from PyPI,
  together with its dependencies (`mcp`, `playwright`, `cryptography`, `keyring`, `websockets`,
  `pypdf`), and runs it on your computer over stdio. `uv.lock` in this plugin records the exact
  versions and file hashes of that release and its dependencies.
- **Browser:** it uses your installed Chrome. Without Chrome, it downloads Playwright's Chromium
  once (about 300 MB) from Playwright's servers, and falls back to Edge if that fails. Sign-in
  windows open your own Chrome with a throwaway profile and a DevTools port bound to `127.0.0.1`
  only, so Assertify can read the new login's cookies. The throwaway profile is deleted afterwards.
- **What it stores:** saved logins (cookies and site storage) in `~/.assertify-mcp/profiles/`,
  encrypted with a key kept in your system keychain (macOS Keychain, Windows Credential Manager or
  Secret Service). Screenshots and downloads go to folders under `~/.assertify-mcp/` unless you pick
  another place.
- **Network:** the browser connects only to the websites you or Claude open in a session. A
  session can be fenced to a list of allowed domains. Assertify has no telemetry, no analytics and
  no Assertify server; nothing is sent to the author.
- **Passwords:** you type them into the site's own sign-in page in a visible window. Claude never
  sees them. Passwords for a browser's own sign-in box (HTTP Basic) are typed into a local form and
  stored encrypted with the login.
- **Safety pauses:** clicks that send, post, buy, delete or connect, and pressing Enter in those
  places, return a pause for your approval instead of acting.

The optional phone relay (`assertify relay`) is not started by this plugin.

## Getting started

After installing, ask Claude something like:

> Log me in to GitHub with Assertify, then show my open pull requests.

A browser window opens for you to sign in. Close it when you're done, and Claude carries on.

## Source and license

Source code, issues and full documentation: https://github.com/romaklym/assertify

Privacy policy: https://github.com/romaklym/assertify/blob/main/PRIVACY.md

MIT licensed. See [LICENSE](LICENSE).
