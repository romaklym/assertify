# Security policy

Assertify holds logged-in sessions for real accounts, so security reports are taken seriously.

## Reporting a vulnerability

Please **do not open a public issue**. Use GitHub's private
[security advisory form](https://github.com/romaklym/assertify-mcp/security/advisories/new) instead.
You'll get a reply within a few days.

Helpful to include: what an attacker can do, steps to reproduce, and the version or commit.

## What's in scope

- Reading or decrypting saved sessions without the user's key
- Escaping the domain guard (navigating a logged-in session to a domain it isn't allowed on)
- Cookies, tokens or password values leaking into tool results, logs or screenshots on disk
- A web page (prompt injection) getting the server to do something the tools don't allow

## Out of scope

- Anything that requires already running code as the user while their keychain is unlocked.
  That access can already read the user's own browser cookies.
- What an agent chooses to do with tools you gave it. Only connect agents you trust.
