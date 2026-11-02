"""Command line: `assertify serve | login | list | delete`."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

from .vault import Vault, VaultError


async def _login(profile: str, url: str, domains: list[str]) -> None:
    from .browser import BrowserManager

    m = BrowserManager()
    try:
        await m.start_login(profile, url, domains)
        print(f"A browser window is open at {url}. Log in there (including any 2FA).")
        print("When you're done, close the browser window or press Enter here.")
        closed = asyncio.create_task(m.logins[profile].done.wait())
        enter = asyncio.create_task(_wait_for_enter())
        await asyncio.wait({closed, enter}, return_when=asyncio.FIRST_COMPLETED)
        enter.cancel()
        print(await m.wait_login(profile) if closed.done() else await m.complete_login(profile))
    finally:
        await m.shutdown()


async def _wait_for_enter() -> None:
    """Wait for Enter without a blocking thread, so closing the window can end the command."""
    loop = asyncio.get_running_loop()
    fut = loop.create_future()
    try:
        loop.add_reader(sys.stdin, lambda: fut.done() or (sys.stdin.readline(), fut.set_result(None)))
    except (NotImplementedError, ValueError):  # Windows / no stdin: rely on closing the window
        return await asyncio.Event().wait()
    try:
        await fut
    finally:
        loop.remove_reader(sys.stdin)


def main() -> None:
    p = argparse.ArgumentParser(prog="assertify")
    sub = p.add_subparsers(dest="cmd")
    sub.add_parser("setup", help="One-time setup: install the browser, check encryption, show how to connect")
    sub.add_parser("serve", help="Run the MCP server over stdio (default)")
    lg = sub.add_parser("login", help="Log in to a site in a visible browser and save the session")
    lg.add_argument("profile")
    lg.add_argument("url")
    lg.add_argument("--domain", action="append", default=[], help="Allowed domain (repeatable)")
    sub.add_parser("list", help="List saved sessions")
    dl = sub.add_parser("delete", help="Delete a saved session")
    dl.add_argument("profile")
    args = p.parse_args()

    try:
        if args.cmd in (None, "serve"):
            from .server import run

            run()
        elif args.cmd == "setup":
            from .install import setup

            sys.exit(setup())
        elif args.cmd == "login":
            asyncio.run(_login(args.profile, args.url, args.domain))
        elif args.cmd == "list":
            print(json.dumps(Vault().list(), indent=2, default=str))
        elif args.cmd == "delete":
            print("Deleted." if Vault().delete(args.profile) else "No such profile.")
    except VaultError as e:
        sys.exit(f"error: {e}")


if __name__ == "__main__":
    main()
