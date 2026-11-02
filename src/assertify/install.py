"""Browser install + `assertify setup`.

Python packages can't run code at install time, so the browser download happens either in
`assertify setup` (recommended, right after installing) or automatically on first use.
"""

from __future__ import annotations

import asyncio
import os
import platform
import subprocess
import sys
from pathlib import Path

from playwright.async_api import Playwright

FALLBACK_CHANNELS = ["chrome", "msedge"]  # the user's own Chrome / Edge, if installed


def install_chromium(out=None) -> bool:
    """Download Playwright's Chromium (about 300 MB, once). Output goes to `out` (stderr by default,
    because stdout is the MCP protocol channel when running as a server)."""
    out = out or sys.stderr
    print("assertify: downloading Chromium (one time, about 300 MB)...", file=out, flush=True)
    cmd = [sys.executable, "-m", "playwright", "install", "chromium"]
    result = subprocess.run(cmd, stdout=out, stderr=out)
    return result.returncode == 0


async def launch(pw: Playwright, **kwargs):
    """Launch Chromium; if it's missing, install it, else fall back to the user's Chrome/Edge."""
    try:
        return await pw.chromium.launch(**kwargs)
    except Exception as e:
        if "Executable doesn't exist" not in str(e):
            raise
    if os.environ.get("ASSERTIFY_NO_AUTO_INSTALL") != "1":
        if await asyncio.to_thread(install_chromium):
            return await pw.chromium.launch(**kwargs)
    for channel in FALLBACK_CHANNELS:
        try:
            browser = await pw.chromium.launch(channel=channel, **kwargs)
            print(f"assertify: using your installed {channel} (Chromium not available)", file=sys.stderr)
            return browser
        except Exception:
            continue
    raise RuntimeError(
        "No browser available: Chromium couldn't be downloaded and no Chrome/Edge was found. "
        "Run `assertify setup` in a terminal to fix this."
    )


def _mcp_command() -> list[str]:
    """Absolute command that runs this exact install, wherever it lives."""
    return [sys.executable, "-m", "assertify.cli", "serve"]


def setup() -> int:
    from playwright.sync_api import sync_playwright

    from .vault import Vault, VaultError, vault_home

    ok = True
    print("assertify setup\n")

    # 1. Browser
    with sync_playwright() as pw:
        have = Path(pw.chromium.executable_path).exists()
    if have:
        print("✓ Chromium is installed")
    else:
        print("… Chromium not found, installing it now")
        if install_chromium(out=sys.stdout):
            print("✓ Chromium installed")
        else:
            ok = False
            print("✗ Chromium download failed. Check your connection and run `assertify setup` again.")
            print("  (assertify will still use Google Chrome or Microsoft Edge if one is installed.)")
    if platform.system() == "Linux":
        print("  Linux: if the browser fails to start, install its system libraries with:")
        print(f"    sudo {sys.executable} -m playwright install-deps chromium")

    # 2. Encryption key
    try:
        _ = Vault().key
        source = "ASSERTIFY_PASSPHRASE" if os.environ.get("ASSERTIFY_PASSPHRASE") else "OS keychain"
        print(f"✓ Encryption key ready ({source}); vault at {vault_home()}")
    except VaultError as e:
        ok = False
        print(f"✗ {e}")

    # 3. How to connect it
    cmd = " ".join(f'"{c}"' if " " in c else c for c in _mcp_command())
    print("\nConnect it to your AI client:")
    print(f"  Claude Code:  claude mcp add -s user assertify -- {cmd}")
    args = ", ".join(f'"{c}"' for c in _mcp_command()[1:])
    print(f'  JSON config:  "assertify": {{"command": "{sys.executable}", "args": [{args}]}}')
    print("\nThen save a login, e.g.:  assertify login github https://github.com/login")
    return 0 if ok else 1
