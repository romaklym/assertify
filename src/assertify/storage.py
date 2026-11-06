"""What a login keeps besides cookies: localStorage, sessionStorage and IndexedDB (apps like
WhatsApp Web and Teams keep their sign-in there), plus per-login browser settings.

A saved state is Playwright's storage_state ({"cookies", "origins"}) with extra keys that
Playwright doesn't know about, so they're split off before a context is made from it."""

from __future__ import annotations

import json

# Runs in a page: [origin, localStorage, sessionStorage, IndexedDB or null].
# IndexedDB is dumped in Playwright's storage_state format. A database holding values that
# don't survive JSON (Blobs, Dates, ArrayBuffers...) is left out rather than saved half-broken,
# and null means "couldn't read it" (keep what was saved before).
STORAGE_JS = r"""
async (withIdb) => {
  const entries = (s) => { try { return Object.entries(s).map(([name, value]) => ({name, value})); } catch (e) { return []; } };
  const out = [location.origin, entries(localStorage), entries(sessionStorage), null];
  if (!withIdb || !self.indexedDB || !indexedDB.databases) return out;
  const plain = (v, depth) => {
    if (v === null || typeof v === 'string' || typeof v === 'boolean') return true;
    if (typeof v === 'number') return Number.isFinite(v);
    if (depth > 40 || typeof v !== 'object') return false;
    if (Array.isArray(v)) return v.every((x) => plain(x, depth + 1));
    const proto = Object.getPrototypeOf(v);
    if (proto !== Object.prototype && proto !== null) return false;
    return Object.values(v).every((x) => plain(x, depth + 1));
  };
  const req = (r) => new Promise((ok, fail) => { r.onsuccess = () => ok(r.result); r.onerror = () => fail(r.error); });
  const LIMIT = 20 * 1024 * 1024;
  let size = 0;
  const dump = async () => {
    const dbs = [];
    for (const info of await indexedDB.databases()) {
      if (!info.name || !info.version) continue;
      const db = await req(indexedDB.open(info.name));
      try {
        const names = [...db.objectStoreNames];
        const stores = [];
        let ok = true;
        if (names.length) {
          const tx = db.transaction(names, 'readonly');
          for (const name of names) {
            const st = tx.objectStore(name);
            const [keys, values] = await Promise.all([req(st.getAllKeys()), req(st.getAll())]);
            const records = [];
            for (let i = 0; i < keys.length; i++) {
              if (!plain(values[i], 0) || (st.keyPath === null && !plain(keys[i], 0))) { ok = false; break; }
              const rec = {value: values[i]};
              if (st.keyPath === null) rec.key = keys[i];
              size += JSON.stringify(rec).length;
              if (size > LIMIT) throw new Error('too big');
              records.push(rec);
            }
            if (!ok) break;
            stores.push({
              name, records, autoIncrement: st.autoIncrement,
              keyPath: typeof st.keyPath === 'string' ? st.keyPath : undefined,
              keyPathArray: Array.isArray(st.keyPath) ? st.keyPath : undefined,
              indexes: [...st.indexNames].map((n) => { const ix = st.index(n); return {
                name: ix.name, unique: ix.unique, multiEntry: ix.multiEntry,
                keyPath: typeof ix.keyPath === 'string' ? ix.keyPath : undefined,
                keyPathArray: Array.isArray(ix.keyPath) ? ix.keyPath : undefined}; }),
            });
          }
        }
        if (ok) dbs.push({name: info.name, version: info.version, stores});
      } finally { db.close(); }
    }
    return dbs;
  };
  try {
    out[3] = await Promise.race([dump(), new Promise((_, fail) => setTimeout(() => fail(new Error('slow')), 10000))]);
  } catch (e) {}
  return out;
}
"""

# Read sessionStorage of the open tabs of an agent session (Playwright's storage_state skips it).
SESSION_JS = "() => [location.origin, Object.entries(sessionStorage).map(([name, value]) => ({name, value}))]"

# Extra keys kept next to Playwright's state in the vault. Never part of meta: list_profiles shows meta.
EXTRA_KEYS = ("session_storage", "http_credentials", "ignore_https_errors")


def split(state: dict | None) -> tuple[dict | None, dict]:
    """Saved state -> (what Playwright accepts as storage_state, the extras)."""
    if not state:
        return None, {}
    pw = {"cookies": state.get("cookies", []), "origins": state.get("origins", [])}
    return pw, {k: state[k] for k in EXTRA_KEYS if k in state}


def merge(pw_state: dict, extras: dict) -> dict:
    return {**pw_state, **{k: v for k, v in extras.items() if v not in (None, {}, [])}}


def clean_idb(dbs: list) -> list:
    """A page's missing keyPath comes back as None; Playwright wants the key left out."""
    for db in dbs:
        for st in db.get("stores", []):
            for d in (st, *st.get("indexes", [])):
                for k in ("keyPath", "keyPathArray"):
                    if d.get(k) is None:
                        d.pop(k, None)
    return dbs


def context_options(extras: dict) -> dict:
    """new_context() keyword arguments for a login's browser settings."""
    opts: dict = {}
    if extras.get("http_credentials"):
        opts["http_credentials"] = extras["http_credentials"]
    if extras.get("ignore_https_errors"):
        opts["ignore_https_errors"] = True
    return opts


def session_storage_script(saved: dict[str, list]) -> str | None:
    """An init script that puts saved sessionStorage back in each new tab of those sites.
    It only fills a tab whose sessionStorage is still empty, so it never overwrites the app's own."""
    data = {o: {i["name"]: i["value"] for i in items} for o, items in (saved or {}).items() if items}
    if not data:
        return None
    return (
        "(() => { try { const d = " + json.dumps(data) + "[location.origin];"
        " if (!d || sessionStorage.length) return;"
        " for (const [k, v] of Object.entries(d)) sessionStorage.setItem(k, v); } catch (e) {} })();"
    )
