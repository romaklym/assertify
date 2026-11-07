# Privacy policy

Last updated: 7 November 2026

Assertify is open-source software that runs on your own computer. It has no account, no server and
no telemetry. The author doesn't receive, collect or store any of your data.

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

Assertify sends nothing to the author or to any other third party.

## Your passwords

You type passwords into the site's own sign-in page in a visible window. The AI agent never sees
them.

## Phone relay (optional)

If you choose to run `assertify relay`, your logins stay on your phone. The relay, which you host
yourself, passes commands and page snapshots between your AI client and the phone. It isn't run by
the author.

## Contact

Questions or concerns: open an issue at https://github.com/romaklym/assertify/issues
