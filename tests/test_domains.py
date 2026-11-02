import pytest

from assertify.browser import _base_domain, host_allowed


@pytest.mark.parametrize(
    "url, expected",
    [
        ("https://github.com/login", "github.com"),
        ("https://www.linkedin.com/login", "linkedin.com"),
        ("https://app.example.co.uk/x", "example.co.uk"),
        ("http://localhost:8000/", "localhost"),
    ],
)
def test_base_domain(url, expected):
    assert _base_domain(url) == expected


@pytest.mark.parametrize(
    "url, allowed",
    [
        ("https://github.com/settings", True),
        ("https://gist.github.com/", True),
        ("https://evilgithub.com/", False),
        ("https://github.com.evil.io/", False),
        ("https://example.com/", False),
        ("about:blank", True),
    ],
)
def test_host_allowed(url, allowed):
    assert host_allowed(url, ["github.com"]) is allowed


def test_empty_allowlist_allows_everything():
    assert host_allowed("https://anything.io/", [])
