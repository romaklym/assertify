# Changelog

## 0.1.0 (2026-11-02)

First public release.

- Log in once in a visible browser; the session is saved encrypted (AES-256-GCM, OS keychain key).
- Headless, logged-in browser sessions for agents: snapshot, click, type, select, scroll, navigate, read, tabs.
- Screenshots shown to the agent and saved locally; optional screenshot on every step.
- Per-login domain guard.
- `assertify setup` installs the browser; automatic download or Chrome/Edge fallback on first use.
- Claude Desktop extension (`.mcpb`) and MCP Registry listing.
