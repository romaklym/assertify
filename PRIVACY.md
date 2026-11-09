# Privacy policy

Last updated: 9 November 2026

Assertify is open-source software that runs on your own computer. It has no accounts and no
telemetry. The optional hosted relay at assertify.co, which lets Claude, ChatGPT and Codex reach your
computer, is described below; it passes data through without storing it.

## What Assertify stores, and where

Everything stays on your computer, in `~/.assertify-mcp/` (or the folder set in `ASSERTIFY_HOME`):

- **Saved logins:** the cookies and site storage of each site you log in to, encrypted with a key
  kept in your system keychain (macOS Keychain, Windows Credential Manager or Secret Service on
  Linux). Passwords for a browser's own sign-in box (HTTP Basic) are stored encrypted with the login.
- **Screenshots and downloads** you or your AI agent ask for.

You can delete a saved login at any time (`assertify delete <name>`, or ask your agent), or delete
the whole folder.

## What it sends, and to whom

- **Websites you use:** the browser connects only to the sites you or your agent open, exactly as
  your normal browser would. Each site's own privacy policy applies to what it receives.
- **Your AI client:** page outlines, text and screenshots that the agent asks for are returned to
  the AI client you connected (Claude, Codex or another). That client's privacy policy applies.
- **Software downloads:** installing Assertify downloads packages from PyPI, and Assertify may
  download Playwright's Chromium browser once if Chrome isn't installed.

Without the hosted relay, Assertify sends nothing to the author or to any other third party.

## The hosted relay (assertify.co)

When you add Assertify to an AI app through `https://assertify.co/mcp` and run
`assertify connect`, the relay, run by the author, passes data between that app and your computer.

- **Passed through, not stored:** tool calls from the AI app and their results (page outlines,
  page text, screenshots, downloaded files the agent asked for). They're held in memory only while
  a call is in flight and aren't logged or kept.
- **Stored, to make sign-in work:** each AI app's registration (its name and redirect address), a
  random ID for your computer with the name it reports (its hostname), the list of tools it offers,
  when it last connected, and SHA-256 hashes of the access tokens and codes. Tokens expire (access
  after 24 hours, refresh after 90 days) and are deleted then.
- **Never sent to the relay:** your saved logins, cookies, site storage, passwords and the
  encryption key. They stay on your computer.
- **Server logs:** the hosting provider (Fly.io) and the relay record standard request logs (time,
  path, status, IP address) for operating and securing the service, kept for at most 30 days.
- **Removing your data:** `assertify unlink` deletes your computer's record and revokes every token
  linked to it.

The relay isn't used for advertising, isn't sold or shared, and isn't used to train models.

## Your passwords

You type passwords into the site's own sign-in page in a visible window. The AI agent never sees
them.

## Phone relay (optional)

If you choose to run `assertify relay`, your logins stay on your phone. The relay, which you host
yourself, passes commands and page snapshots between your AI client and the phone. It isn't run by
the author.

## Contact

Questions or concerns: open an issue at https://github.com/romaklym/assertify/issues
