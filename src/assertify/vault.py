"""Encrypted on-disk storage for browser sessions.

Each profile is one file: ~/.assertify-mcp/profiles/<name>.enc
Contents (after decryption) are JSON: {"meta": {...}, "state": <Playwright storage_state>}.

Encryption: AES-256-GCM. The profile name is bound in as associated data,
so an encrypted file can't be renamed to impersonate another profile.

Key source (first match wins):
  1. ASSERTIFY_PASSPHRASE env var -> scrypt-derived key (salt stored in vault dir)
  2. OS keychain (macOS Keychain / Windows Credential Locker / Secret Service)
     via `keyring`; a random key is generated on first use.
"""

from __future__ import annotations

import json
import os
import re
import secrets
import time
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

MAGIC = b"AS1"
KEYRING_SERVICE = "assertify-mcp"
KEYRING_USER = "master-key"
NAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.@+-]{0,63}$")  # emails work as names


class VaultError(Exception):
    pass


def vault_home() -> Path:
    home = Path(os.environ.get("ASSERTIFY_HOME", Path.home() / ".assertify-mcp"))
    (home / "profiles").mkdir(parents=True, exist_ok=True)
    os.chmod(home, 0o700)
    os.chmod(home / "profiles", 0o700)
    return home


def _load_key() -> bytes:
    passphrase = os.environ.get("ASSERTIFY_PASSPHRASE")
    if passphrase:
        salt_file = vault_home() / "salt"
        if not salt_file.exists():
            salt_file.write_bytes(secrets.token_bytes(16))
            os.chmod(salt_file, 0o600)
        kdf = Scrypt(salt=salt_file.read_bytes(), length=32, n=2**15, r=8, p=1)
        return kdf.derive(passphrase.encode())

    try:
        import keyring

        stored = keyring.get_password(KEYRING_SERVICE, KEYRING_USER)
        if stored is None:
            stored = secrets.token_hex(32)
            keyring.set_password(KEYRING_SERVICE, KEYRING_USER, stored)
        return bytes.fromhex(stored)
    except Exception as e:  # no usable keychain (e.g. headless Linux)
        raise VaultError("No OS keychain available. Set ASSERTIFY_PASSPHRASE to use a passphrase instead.") from e


class Vault:
    def __init__(self) -> None:
        self.dir = vault_home() / "profiles"
        self._key: bytes | None = None

    @property
    def key(self) -> bytes:
        if self._key is None:
            self._key = _load_key()
        return self._key

    def _path(self, name: str) -> Path:
        if not NAME_RE.match(name):
            raise VaultError(f"Invalid profile name {name!r}: use letters, digits, '_', '-', '.', '@', '+' (max 64).")
        return self.dir / f"{name}.enc"

    def save(self, name: str, state: dict, meta: dict[str, Any]) -> None:
        path = self._path(name)
        meta = {**meta, "name": name, "updated_at": time.time()}
        meta.setdefault("created_at", meta["updated_at"])
        plaintext = json.dumps({"meta": meta, "state": state}).encode()
        nonce = secrets.token_bytes(12)
        blob = MAGIC + nonce + AESGCM(self.key).encrypt(nonce, plaintext, name.encode())
        tmp = path.with_suffix(".tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "wb") as f:
            f.write(blob)
        os.replace(tmp, path)  # atomic: never leaves a half-written profile

    def load(self, name: str) -> tuple[dict, dict]:
        path = self._path(name)
        if not path.exists():
            raise VaultError(f"No saved session named {name!r}. Log in first.")
        blob = path.read_bytes()
        if not blob.startswith(MAGIC):
            raise VaultError(f"{path} is not an Assertify file.")
        nonce, ct = blob[3:15], blob[15:]
        try:
            data = json.loads(AESGCM(self.key).decrypt(nonce, ct, name.encode()))
        except Exception as e:
            raise VaultError(f"Could not decrypt {name!r} (wrong key/passphrase or file tampered).") from e
        return data["state"], data["meta"]

    def list(self, site: str | None = None) -> list[dict]:
        """All saved logins, or only those for one site ("google.com", "gmail", "linkedin")."""
        out = []
        for p in sorted(self.dir.glob("*.enc")):
            try:
                state, meta = self.load(p.stem)
                meta = {**meta, "cookies": len(state.get("cookies", []))}
            except VaultError as e:
                meta = {"name": p.stem, "error": str(e)}
            out.append(meta)
        if site:
            out = [m for m in out if _matches_site(m, site)]
        return out

    def exists(self, name: str) -> bool:
        return self._path(name).exists()

    def rename(self, old: str, new: str, overwrite: bool = False) -> None:
        """Re-encrypt under the new name (the name is bound into the ciphertext)."""
        if old == new:
            return
        case_only = old.lower() == new.lower()  # same file on macOS/Windows, which ignore case
        if not case_only and self.exists(new) and not overwrite:
            raise VaultError(f"A profile named {new!r} already exists.")
        state, meta = self.load(old)
        if case_only:
            self.delete(old)
        self.save(new, state, meta)
        if not case_only:
            self.delete(old)

    def delete(self, name: str) -> bool:
        path = self._path(name)
        if path.exists():
            path.unlink()
            return True
        return False


def _matches_site(meta: dict, site: str) -> bool:
    q = site.lower().removeprefix("https://").removeprefix("http://").removeprefix("www.").strip("/")
    for d in [meta.get("site") or "", *(meta.get("allowed_domains") or [])]:
        if d and (q == d or d.endswith("." + q) or q.endswith("." + d) or q in d.split(".")):
            return True
    return q in (meta.get("start_url") or "")
