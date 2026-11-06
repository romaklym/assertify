"""Downloads, the browser's own sign-in box, and logins kept outside cookies. Needs Chromium."""

import asyncio
import base64
import io
import threading
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from assertify import files, install, storage
from assertify.browser import BrowserManager, PendingLogin, _disposition_name
from assertify.vault import Vault

CSV = b"name,amount\nAlice,10\nBob,20\n"


def _xlsx() -> bytes:
    buf = io.BytesIO()
    m = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
    r = 'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"'
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr(
            "xl/workbook.xml",
            f'<workbook {m} {r}><sheets><sheet name="Q1" sheetId="1" r:id="rId1"/></sheets></workbook>',
        )
        z.writestr(
            "xl/_rels/workbook.xml.rels",
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Target="worksheets/sheet1.xml"/></Relationships>',
        )
        z.writestr(
            "xl/sharedStrings.xml", f"<sst {m}><si><t>Item</t></si><si><t>Cost</t></si><si><t>Desk</t></si></sst>"
        )
        z.writestr(
            "xl/worksheets/sheet1.xml",
            f'<worksheet {m}><sheetData><row r="1"><c r="A1" t="s"><v>0</v></c><c r="B1" t="s"><v>1</v></c></row>'
            '<row r="2"><c r="A2" t="s"><v>2</v></c><c r="C2"><v>99</v></c></row></sheetData></worksheet>',
        )
    return buf.getvalue()


PAGES = {
    "/export": (
        "text/html",
        b"""<!doctype html><title>Reports</title><h1>Reports</h1>
<a href="/report.csv">Export CSV</a> <a href="/page">Not a file</a>
<script>sessionStorage.setItem('tab', sessionStorage.getItem('tab') || 'fresh')</script>""",
    ),
    "/page": ("text/html", b"<!doctype html><title>Page</title><p>just a page</p>"),
    # Like Discord: the sign-in token lives in localStorage, and the app hides localStorage once loaded.
    "/app": (
        "text/html",
        b"""<!doctype html><title>Chat</title><body><script>
const ls = localStorage, token = ls.getItem('token');
Object.defineProperty(window, 'localStorage', {get() { throw new Error('hidden'); }});
const show = (t) => { document.body.innerHTML = t ? '<h1>Signed in</h1>' : '<h1>Log in</h1><button>Log in</button>';
  const b = document.querySelector('button'); if (b) b.onclick = () => { ls.setItem('token', '"t0k"'); show(1); }; };
show(token);
</script></body>""",
    ),
    "/report.xlsx": ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", _xlsx()),
    # An app that keeps things JSON can't hold in IndexedDB, plus a key the browser won't export.
    "/idb": (
        "text/html",
        b"""<!doctype html><title>Vault app</title><body><script>
(async () => {
  if ((await indexedDB.databases()).some((d) => d.name === 'app')) { window.done = true; return; }
  const k = await crypto.subtle.generateKey({name: 'AES-GCM', length: 128}, true, ['encrypt', 'decrypt']);
  const locked = await crypto.subtle.generateKey({name: 'AES-GCM', length: 128}, false, ['encrypt']);
  const put = (name, store, entries) => new Promise((ok, fail) => { const o = indexedDB.open(name, 1);
    o.onupgradeneeded = () => o.result.createObjectStore(store);
    o.onsuccess = () => { const tx = o.result.transaction(store, 'readwrite');
      for (const [key, v] of entries) tx.objectStore(store).put(v, key);
      tx.oncomplete = () => { o.result.close(); ok(); }; tx.onerror = fail; }; });
  await put('app', 'kv', [['me', {when: new Date(5), bytes: new Uint8Array([1, 2, 3]),
    file: new Blob(['hi'], {type: 'text/plain'}), tags: new Set(['a']), big: 10n, nan: NaN, key: k,
    raw: JSON.stringify(await crypto.subtle.exportKey('jwk', k))}], [new Date(7), 'date key']]);
  await put('locked', 'keys', [['k', locked]]);
  window.done = true;
})();
</script></body>""",
    ),
}

READ_IDB = """async () => {
  const o = indexedDB.open('app'); const db = await new Promise((r) => o.onsuccess = () => r(o.result));
  const get = (k) => new Promise((r) => { const g = db.transaction('kv').objectStore('kv').get(k); g.onsuccess = () => r(g.result); });
  const v = await get('me'), d = await get(new Date(7));
  const jwk = await crypto.subtle.exportKey('jwk', v.key);
  return [v.when.getTime(), Array.from(v.bytes), v.bytes.constructor.name, await v.file.text(), v.file.type, [...v.tags],
    String(v.big), Number.isNaN(v.nan), jwk.k === JSON.parse(v.raw).k, d, (await indexedDB.databases()).map((x) => x.name)]; }"""
RESTORED = [5, [1, 2, 3], "Uint8Array", "hi", "text/plain", ["a"], "10", True, True, "date key", ["app"]]


class Site(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/report.csv":
            self.send_response(200)
            self.send_header("Content-Type", "text/csv")
            self.send_header("Content-Disposition", 'attachment; filename="q1 report.csv"')
            self.end_headers()
            self.wfile.write(CSV)
            return
        if self.path == "/intranet":
            want = "Basic " + base64.b64encode(b"tester:pw").decode()
            if self.headers.get("Authorization") != want:
                self.send_response(401)
                self.send_header("WWW-Authenticate", 'Basic realm="intranet"')
                self.end_headers()
                return
        ctype, body = PAGES.get(self.path, ("text/html", b"<!doctype html><title>Intranet</title><h1>Welcome in</h1>"))
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


@pytest.fixture
def site():
    server = ThreadingHTTPServer(("127.0.0.1", 0), Site)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()


def _save(url: str, **extras) -> None:
    Vault().save(
        "t", storage.merge({"cookies": [], "origins": []}, extras), {"start_url": url, "allowed_domains": ["127.0.0.1"]}
    )


# ---------- reading files ----------


def test_csv_becomes_a_table(tmp_path):
    p = tmp_path / "r.csv"
    p.write_bytes(CSV)
    assert files.read(p).splitlines()[:3] == ["| name | amount |", "| --- | --- |", "| Alice | 10 |"]


def test_xlsx_becomes_a_table(tmp_path):
    p = tmp_path / "r.xlsx"
    p.write_bytes(_xlsx())
    text = files.read(p)
    assert "### Sheet: Q1" in text and "| Desk |  | 99 |" in text


def test_unknown_files_are_not_shown(tmp_path):
    p = tmp_path / "x.zip"
    p.write_bytes(b"PK\x03\x04")
    assert files.read(p) is None


def test_names_are_made_safe():
    assert files.safe_name("../../.ssh/id_rsa") == "id_rsa"
    assert files.safe_name("a/b\\c:d.csv") == "c_d.csv"
    assert files.safe_name("...") == "download"
    assert _disposition_name("attachment; filename*=UTF-8''r%C3%A9sum%C3%A9.pdf") == "résumé.pdf"
    assert _disposition_name('attachment; filename="q1 report.csv"') == "q1 report.csv"


def test_unreadable_storage_keeps_what_was_saved():
    login = PendingLogin("t", None, None, {})
    login.keep("https://a.test", [{"name": "token", "value": "x"}], [], None)
    login.keep("https://a.test", None, None, None)  # the page hid its storage this time
    assert login.local_storage["https://a.test"] == [{"name": "token", "value": "x"}]
    assert storage.summary(login.state()) == {"local_storage_items": 1}


def test_extras_stay_out_of_playwright_state():
    pw, extras = storage.split({"cookies": [], "origins": [], "http_credentials": {"username": "u"}, "x": 1})
    assert pw == {"cookies": [], "origins": []} and extras == {"http_credentials": {"username": "u"}}


# ---------- in a browser ----------


def test_download_by_click_and_url(site, monkeypatch):
    monkeypatch.setattr("assertify.browser.DOWNLOAD_WAIT", 2)
    asyncio.run(asyncio.wait_for(_download_by_click_url_and_latest(site), 90))


def test_http_auth_from_the_vault(site):
    asyncio.run(asyncio.wait_for(_http_auth_from_the_vault(site), 90))


def test_session_storage_is_saved_and_restored(site):
    asyncio.run(asyncio.wait_for(_session_storage_is_saved_and_restored(site), 90))


def test_login_kept_in_hidden_local_storage(site, monkeypatch):
    real = install.launch
    monkeypatch.setattr("assertify.browser.native_supported", lambda: False)
    monkeypatch.setattr("assertify.browser.launch", lambda pw, headless=True, **kw: real(pw, headless=True, **kw))
    asyncio.run(asyncio.wait_for(_login_kept_in_hidden_local_storage(site), 90))


async def _login_kept_in_hidden_local_storage(site):
    m = BrowserManager()
    try:
        await m.start_login("t", site + "/app", ["127.0.0.1"])
        page = m.logins["t"].context.pages[0]
        await page.wait_for_selector("button")
        await page.click("button")  # the user signs in
        await asyncio.sleep(2)  # a backup tick reads it while the window is open
        result = await m.complete_login("t")
        assert "1 localStorage items" in result
        state, _ = Vault().load("t")
        assert state["origins"][0]["localStorage"] == [{"name": "token", "value": '"t0k"'}]
        assert Vault().list()[0]["local_storage_items"] == 1
        s = await m.open_session("t")
        assert "Signed in" in await s.active.inner_text("body")
    finally:
        await m.shutdown()


def test_indexed_db_with_files_and_keys(site, monkeypatch):
    real = install.launch
    monkeypatch.setattr("assertify.browser.native_supported", lambda: False)
    monkeypatch.setattr("assertify.browser.launch", lambda pw, headless=True, **kw: real(pw, headless=True, **kw))
    asyncio.run(asyncio.wait_for(_indexed_db_with_files_and_keys(site), 90))


async def _indexed_db_with_files_and_keys(site):
    m = BrowserManager()
    try:
        await m.start_login("t", site + "/idb", ["127.0.0.1"])
        await m.logins["t"].context.pages[0].wait_for_function("window.done")
        result = await m.complete_login("t")
        assert "locked (encryption keys the browser won't let be copied)" in result
        meta = Vault().list()[0]
        assert meta["indexed_db_databases"] == 1 and "locked" in meta["storage_not_copied"][0]
        s = await m.open_session("t")
        await s.active.wait_for_function("window.done")
        assert await s.active.evaluate(READ_IDB) == RESTORED
        await m.close_session(s.id)  # saving again keeps every type
        s = await m.open_session("t")
        await s.active.wait_for_function("window.done")
        assert await s.active.evaluate(READ_IDB) == RESTORED
    finally:
        await m.shutdown()


def test_older_saves_move_to_the_new_format():
    plain = [{"name": "db", "version": 1, "stores": [{"name": "s", "records": [{"value": 1, "key": "a"}]}]}]
    coded = [{"name": "db", "version": 1, "stores": [{"name": "s", "records": [{"valueEncoded": {"d": "x"}}]}]}]
    pw, extras = storage.split(
        {
            "cookies": [],
            "origins": [
                {"origin": "https://a.test", "indexedDB": plain},
                {"origin": "https://b.test", "indexedDB": coded},
            ],
        }
    )
    assert extras["indexed_db"] == {"https://a.test": plain}
    assert "indexedDB" not in pw["origins"][0] and pw["origins"][1]["indexedDB"] == coded


async def _download_by_click_url_and_latest(site):
    _save(site + "/export")
    m = BrowserManager()
    try:
        s = await m.open_session("t")
        await m.snapshot(s.id)
        note, path, ctype = await m.download(s, None, "Export CSV", None, False)
        assert path.name == "01-q1 report.csv" and path.read_bytes() == CSV
        assert (path.stat().st_mode & 0o777) == 0o600
        note, path, ctype = await m.download(s, None, None, site + "/report.xlsx", False)
        assert path.suffix == ".xlsx" and "Desk" in files.read(path, ctype)
        with pytest.raises(Exception, match="allowed domains"):
            await m.download(s, None, None, "https://example.com/x.csv", False)
        await m.snapshot(s.id)
        with pytest.raises(Exception, match="no download started"):
            await m.download(s, None, "Not a file", None, False)
    finally:
        await m.shutdown()


async def _http_auth_from_the_vault(site):
    _save(site + "/intranet")
    m = BrowserManager()
    try:
        with pytest.raises(Exception, match="browser_settings"):
            await m.open_session("t")
        _save(site + "/intranet", http_credentials={"username": "tester", "password": "pw", "origin": site})
        s = await m.open_session("t")
        assert "Welcome in" in await s.active.inner_text("body")
        await m.close_session(s.id)  # saving keeps the password the user entered
        state, meta = Vault().load("t")
        assert state["http_credentials"]["username"] == "tester" and "http_credentials" not in meta
        assert all("password" not in str(p) for p in m.profiles())
    finally:
        await m.shutdown()


async def _session_storage_is_saved_and_restored(site):
    _save(site + "/export", session_storage={site: [{"name": "tab", "value": "restored"}]})
    m = BrowserManager()
    try:
        s = await m.open_session("t")
        assert await s.active.evaluate("sessionStorage.getItem('tab')") == "restored"
        await s.active.evaluate("sessionStorage.setItem('tab', 'changed')")
        await m.close_session(s.id)
        state, _ = Vault().load("t")
        assert state["session_storage"][site] == [{"name": "tab", "value": "changed"}]
    finally:
        await m.shutdown()
