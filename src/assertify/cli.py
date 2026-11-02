"""Command line: `assertify serve | login | list | delete`."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import threading

from .vault import Vault, VaultError


async def _login(profile: str | None, url: str, domains: list[str], read_only: bool) -> None:
    from .browser import BrowserManager

    m = BrowserManager()
    try:
        await m.start_login(profile, url, domains, read_only=read_only)
        profile = next(iter(m.logins))
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
    """Wait for Enter while still letting a closed window end the command."""
    loop = asyncio.get_running_loop()
    fut = loop.create_future()

    def done() -> None:
        if not fut.done():
            fut.set_result(None)

    try:
        loop.add_reader(sys.stdin, lambda: (sys.stdin.readline(), done()))
    except (NotImplementedError, ValueError, OSError):
        # Windows has no add_reader: read in a daemon thread, which can't keep the process alive.
        def read() -> None:
            try:
                sys.stdin.readline()
            except Exception:
                return
            loop.call_soon_threadsafe(done)

        threading.Thread(target=read, daemon=True).start()
        return await fut
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
    lg.add_argument("args", nargs="+", metavar="[name] url", help="Name is optional: defaults to the account's email")
    lg.add_argument("--domain", action="append", default=[], help="Allowed domain (repeatable)")
    lg.add_argument(
        "--read-only", action="store_true", help="Agents may browse and read, but never type, submit, send or buy"
    )
    ls = sub.add_parser("list", help="List saved sessions")
    ls.add_argument("site", nargs="?", help="Only this site's logins")
    rn = sub.add_parser("rename", help="Rename a saved session")
    rn.add_argument("profile")
    rn.add_argument("new_name")
    dl = sub.add_parser("delete", help="Delete a saved session")
    dl.add_argument("profile")
    args = p.parse_args()
    if args.cmd not in (None, "serve"):
        # Windows consoles may not be UTF-8; never crash on a ✓ or an emoji in a page title.
        for stream in (sys.stdout, sys.stderr):
            if hasattr(stream, "reconfigure"):
                stream.reconfigure(errors="replace")

    try:
        if args.cmd in (None, "serve"):
            from .server import run

            run()
        elif args.cmd == "setup":
            from .install import setup

            sys.exit(setup())
        elif args.cmd == "login":
            if len(args.args) > 2:
                p.error("login takes [name] url")
            name, url = (None, args.args[0]) if len(args.args) == 1 else args.args
            asyncio.run(_login(name, url, args.domain, args.read_only))
        elif args.cmd == "list":
            print(json.dumps(Vault().list(args.site), indent=2, default=str))
        elif args.cmd == "rename":
            Vault().rename(args.profile, args.new_name)
            print(f"Renamed to {args.new_name!r}.")
        elif args.cmd == "delete":
            print("Deleted." if Vault().delete(args.profile) else "No such profile.")
    except VaultError as e:
        sys.exit(f"error: {e}")


if __name__ == "__main__":
    main()
