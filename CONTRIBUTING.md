# Contributing to Assertify

Thanks for helping! Bug reports, site compatibility notes and PRs are all welcome.

## Setup

```bash
git clone https://github.com/romaklym/assertify.git
cd assertify
uv sync
uv run assertify setup   # downloads Chromium once
```

## Before you open a PR

```bash
uv run ruff format .
uv run ruff check .
uv run pytest
```

`tests/test_e2e.py` runs the real MCP server against a small local site, so it needs Chromium.
Tests use a temporary vault and a passphrase, never your real keychain or saved logins.

## Project layout

| File | What's in it |
|---|---|
| `src/assertify/server.py` | MCP tools |
| `src/assertify/browser.py` | Playwright: login windows, headless sessions, snapshots, screenshots |
| `src/assertify/vault.py` | Encrypted storage and the keychain key |
| `src/assertify/install.py` | `assertify setup` and browser auto-install |
| `src/assertify/cli.py` | Command line |
| `manifest.json` | Claude Desktop extension (`.mcpb`) |
| `server.json` | MCP Registry listing |

## Guidelines

- Keep the agent's view small: tools return compact outlines, not HTML.
- Never log or return cookies, tokens or password values.
- Anything that widens what an agent can do (new tools, fewer guards) should be opt-in.
- Please never include real session files, screenshots of your accounts, or personal data in issues or PRs.
