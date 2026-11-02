import pytest

from assertify import safety


def test_risky_labels():
    for name in ["Send", "Post", "Buy now", "Delete conversation", "Connect", "Place order"]:
        assert safety.risky_label(name), name
    for name in ["Messages", "Search", "Home", "Next", "", "x" * 60 + " send"]:
        assert not safety.risky_label(name), name


def test_click_guard():
    safety.check_click("button", "Next", False, read_only=False, confirmed=False)
    with pytest.raises(safety.Blocked, match="confirmed=true"):
        safety.check_click("button", "Send", False, read_only=False, confirmed=False)
    safety.check_click("button", "Send", False, read_only=False, confirmed=True)
    with pytest.raises(safety.Blocked, match="read-only"):
        safety.check_click("button", "Send", False, read_only=True, confirmed=True)
    with pytest.raises(safety.Blocked, match="read-only"):
        safety.check_click("button", "Go", True, read_only=True, confirmed=False)


def test_submit_and_keys():
    safety.check_submit("Search messages", read_only=True, confirmed=False)  # searching is always fine
    with pytest.raises(safety.Blocked):
        safety.check_submit("Write a message", read_only=False, confirmed=False)
    safety.check_key("Escape", composing=True, read_only=True, confirmed=False)
    with pytest.raises(safety.Blocked):
        safety.check_key("Enter", composing=True, read_only=False, confirmed=False)
    safety.check_key("Enter", composing=False, read_only=False, confirmed=False)


def test_urls_and_sites():
    safety.check_url("https://example.com")
    for bad in ["file:///etc/passwd", "chrome://settings", "javascript:alert(1)", "data:text/html,hi"]:
        with pytest.raises(safety.Blocked):
            safety.check_url(bad)
    assert safety.strict_site(["www.linkedin.com"]) == "LinkedIn"
    assert safety.strict_site(["github.com"]) is None


def test_page_budget(monkeypatch):
    monkeypatch.setenv("ASSERTIFY_MAX_PAGES_PER_HOUR", "3")
    b = safety.PageBudget()
    for _ in range(3):
        b.check("p", "LinkedIn")
        b.record("p")
    with pytest.raises(safety.Blocked, match="LinkedIn"):
        b.check("p", "LinkedIn")
    b.check("other", None)
