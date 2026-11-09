# Assertify plugin

Assertify lets Claude use websites you're logged in to. You sign in once in a real browser window,
the session is saved encrypted on your computer, and Claude can then open that site as you: read
pages, click, type, fill in forms, download files and take screenshots. Actions that send, post,
buy, delete or connect are paused until you approve them.

The plugin contains:

- **An MCP connection** to `https://mcp.assertify.co/mcp`. It relays each tool call to the Assertify
  companion on your own computer, where the browser and your saved logins are.
- **A skill** (`use-websites`) that teaches Claude the login → browse → close flow and the safety rules.

It works in Claude Code, Cowork, claude.ai and Codex, as long as the companion is running on your computer.

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

Then, on the computer whose browser you want to use (needs [uv](https://docs.astral.sh/uv/)):

```
uvx assertify-mcp setup
uvx assertify-mcp connect
```

The first time Claude uses Assertify, it opens an mcp.assertify.co page with a code. Run
`uvx assertify-mcp link CODE` on your computer and confirm the app's name. That links this Claude
(or Codex) to your computer. There's no account or password.

## How it works, and what is sent where

```
Claude --MCP + OAuth--> mcp.assertify.co --WebSocket--> assertify connect (your computer) --> browser
```

- **On your computer:** `assertify connect` runs the open-source
  [`assertify-mcp`](https://pypi.org/project/assertify-mcp/) package. It opens one outbound
  connection to mcp.assertify.co (no open ports). Saved logins are cookies and site storage in
  `~/.assertify-mcp/profiles/`, encrypted with a key kept in your system keychain. Screenshots and
  downloads go to folders under `~/.assertify-mcp/`.
- **mcp.assertify.co:** it relays tool calls and their results (page outlines, text, screenshots)
  between Claude and your computer, and stores none of them. It keeps only what sign-in needs: the
  registered app's name and redirect address, your computer's ID, and hashed tokens. Your logins,
  cookies and keychain key never leave your computer.
- **Websites:** the browser connects only to the sites you or Claude open. A login can be fenced to
  a list of allowed domains.
- **Passwords:** you type them into the site's own sign-in page in a visible window on your computer.
  Claude never sees them.
- **Safety pauses:** clicks that send, post, buy, delete or connect, and pressing Enter in those
  places, return a pause for your approval instead of acting.
- **Revoking access:** `uvx assertify-mcp unlink` revokes every app linked to your computer.
  Stopping `assertify connect` cuts access right away.

Prefer no server at all? Run `uvx assertify-mcp` as a local MCP server instead; see the
[main README](https://github.com/romaklym/assertify#readme).

## Getting started

After installing, ask Claude something like:

> Log me in to GitHub with Assertify, then show my open pull requests.

A browser window opens on your computer for you to sign in. Close it when you're done, and Claude carries on.

## Source and license

Source code, issues and full documentation: https://github.com/romaklym/assertify

Privacy policy: https://github.com/romaklym/assertify/blob/main/PRIVACY.md

MIT licensed. See [LICENSE](LICENSE).
