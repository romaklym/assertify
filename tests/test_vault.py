import stat

import pytest

from assertify.vault import Vault, VaultError

STATE = {"cookies": [{"name": "session_token", "value": "s3cret", "domain": "example.com"}], "origins": []}


def test_round_trip():
    v = Vault()
    v.save("example", STATE, {"start_url": "https://example.com"})
    state, meta = v.load("example")
    assert state == STATE
    assert meta["start_url"] == "https://example.com"
    assert meta["name"] == "example"


def test_file_is_encrypted_and_private(isolated_vault):
    Vault().save("example", STATE, {})
    path = isolated_vault / "profiles" / "example.enc"
    data = path.read_bytes()
    assert b"session_token" not in data and b"s3cret" not in data
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700


def test_wrong_passphrase_is_rejected(monkeypatch):
    Vault().save("example", STATE, {})
    monkeypatch.setenv("ASSERTIFY_PASSPHRASE", "wrong")
    with pytest.raises(VaultError, match="Could not decrypt"):
        Vault().load("example")


def test_renamed_file_is_rejected(isolated_vault):
    """The profile name is bound into the ciphertext, so files can't be swapped."""
    Vault().save("alice", STATE, {})
    (isolated_vault / "profiles" / "alice.enc").rename(isolated_vault / "profiles" / "bob.enc")
    with pytest.raises(VaultError):
        Vault().load("bob")


@pytest.mark.parametrize("name", ["../etc", "a/b", "", ".hidden", "x" * 65])
def test_bad_names_are_rejected(name):
    with pytest.raises(VaultError, match="Invalid profile name"):
        Vault().save(name, STATE, {})


def test_list_and_delete():
    v = Vault()
    v.save("one", STATE, {})
    v.save("two", STATE, {})
    assert [p["name"] for p in v.list()] == ["one", "two"]
    assert v.list()[0]["cookies"] == 1
    assert v.delete("one") is True
    assert v.delete("one") is False
    assert [p["name"] for p in v.list()] == ["two"]
