import pytest


@pytest.fixture(autouse=True)
def isolated_vault(tmp_path, monkeypatch):
    """Every test gets its own empty vault and a passphrase key, never the real keychain."""
    monkeypatch.setenv("ASSERTIFY_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("ASSERTIFY_PASSPHRASE", "test-passphrase")
    monkeypatch.setenv("ASSERTIFY_HUMANIZE", "0")  # no random pauses; test_humanized turns it back on
    return tmp_path / "home"
