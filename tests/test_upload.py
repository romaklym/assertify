"""Uploading files and folders the way a person would: file dialog, hidden field, drag and drop."""

import asyncio
import os
import sys

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from test_e2e import COOKIE, _text, site  # noqa: F401  (site is a fixture)

from assertify import safety
from assertify.vault import Vault

PNG = b"\x89PNG\r\n\x1a\n" + b"\0" * 64


@pytest.fixture
def files(tmp_path):
    d = tmp_path / "trip"
    d.mkdir()
    (d / "beach.png").write_bytes(PNG)
    (d / "sunset.jpg").write_bytes(PNG)
    (d / ".DS_Store").write_bytes(b"x")
    (tmp_path / "cv.pdf").write_bytes(b"%PDF-1.4")
    (tmp_path / "notes.txt").write_text("hi")
    ssh = tmp_path / ".ssh"
    ssh.mkdir()
    (ssh / "id_ed25519").write_text("secret")
    (tmp_path / "server.pem").write_text("secret")
    return tmp_path


def test_folder_expands_and_skips_hidden(files):
    got = safety.upload_paths([str(files / "trip")], files / "home")
    assert [p.name for p in got] == ["beach.png", "sunset.jpg"]


@pytest.mark.parametrize("name", [".ssh/id_ed25519", "server.pem", ".ssh", "home/profiles"])
def test_secrets_are_refused(files, name):
    (files / "home" / "profiles").mkdir(parents=True, exist_ok=True)
    (files / "home" / "profiles" / "x.enc").write_bytes(b"x")
    with pytest.raises(safety.Blocked):
        safety.upload_paths([str(files / name)], files / "home")


def test_relative_and_missing_paths_are_refused(files):
    with pytest.raises(safety.Blocked, match="full path"):
        safety.upload_paths(["photo.png"], files / "home")
    with pytest.raises(safety.Blocked, match="No such"):
        safety.upload_paths([str(files / "nope.png")], files / "home")


def test_upload_dirs_allowlist(files, monkeypatch):
    monkeypatch.setenv("ASSERTIFY_UPLOAD_DIRS", str(files / "trip"))
    safety.upload_paths([str(files / "trip" / "beach.png")], files / "home")
    with pytest.raises(safety.Blocked, match="ASSERTIFY_UPLOAD_DIRS"):
        safety.upload_paths([str(files / "cv.pdf")], files / "home")


async def _run(url: str, files) -> None:
    Vault().save(
        "u", {"cookies": [COOKIE], "origins": []}, {"start_url": url + "upload", "allowed_domains": ["127.0.0.1"]}
    )
    params = StdioServerParameters(command=sys.executable, args=["-m", "assertify", "serve"], env=dict(os.environ))
    async with stdio_client(params) as (r, w), ClientSession(r, w) as s:
        await s.initialize()
        snap = _text(await s.call_tool("open_session", {"profile": "u"}))
        sid = snap.splitlines()[0].split(": ")[1]
        assert "upload field(s)" in snap and "upload_files" in snap, snap

        async def page_text():
            return _text(await s.call_tool("read_text", {"session_id": sid}))

        # A whole folder through the "Photo/video" button's file dialog (like Facebook).
        res = _text(
            await s.call_tool(
                "upload_files", {"session_id": sid, "paths": [str(files / "trip")], "text": "Photo/video"}
            )
        )
        assert "Attached 2 file(s)" in res and "file dialog" in res, res
        assert "Photos: beach.png,sunset.jpg" in await page_text()

        # Drag and drop onto a drop-only area.
        res = _text(
            await s.call_tool(
                "upload_files",
                {"session_id": sid, "paths": [str(files / "trip" / "beach.png")], "text": "Drop files here"},
            )
        )
        assert "dragging" in res, res
        assert f"Dropped: beach.png:{len(PNG)}" in await page_text()

        # No target: pick the field that accepts this file type.
        await s.call_tool("upload_files", {"session_id": sid, "paths": [str(files / "cv.pdf")]})
        assert "CV: cv.pdf" in await page_text()

        # Wrong type, too many for a single-file field, and secrets are refused.
        bad = await s.call_tool(
            "upload_files", {"session_id": sid, "paths": [str(files / "notes.txt")], "text": "Resume"}
        )
        assert bad.is_error and "only accepts" in _text(bad), _text(bad)
        bad = await s.call_tool(
            "upload_files",
            {"session_id": sid, "paths": [str(files / "cv.pdf"), str(files / "notes.txt")], "text": "Resume"},
        )
        assert bad.is_error and "one file" in _text(bad), _text(bad)
        bad = await s.call_tool("upload_files", {"session_id": sid, "paths": [str(files / ".ssh" / "id_ed25519")]})
        assert bad.is_error and "Blocked" in _text(bad)
        await s.call_tool("close_session", {"session_id": sid, "save": False})


def test_upload_end_to_end(site, files):  # noqa: F811
    asyncio.run(asyncio.wait_for(_run(site, files), timeout=90))
