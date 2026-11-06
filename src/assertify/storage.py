"""What a login keeps besides cookies: localStorage, sessionStorage and IndexedDB (apps like
WhatsApp Web and Teams keep their sign-in there), plus per-login browser settings.

A saved state is Playwright's storage_state ({"cookies", "origins"}) with extra keys that
Playwright doesn't know about, so they're split off before a context is made from it."""

from __future__ import annotations

import json

# Runs in a page (in an isolated world, see native.isolated_eval): [origin, localStorage,
# sessionStorage, IndexedDB], each null when it couldn't be read (keep what was saved before).
# IndexedDB comes back as {dbs, skipped}. Values that JSON can't hold (dates, binary data, files,
# Maps, exportable encryption keys...) are wrapped as {"$t": kind, ...} (see RESTORE_IDB_JS).
# A database holding something that can't be copied at all (encryption keys the browser
# won't export) is left out whole and named in `skipped`, rather than saved half-broken.
STORAGE_JS = r"""
async (withIdb) => {
  const entries = (get) => { try { return Object.entries(get()).map(([name, value]) => ({name, value})); } catch (e) { return null; } };
  const out = [location.origin, entries(() => localStorage), entries(() => sessionStorage), null];
  if (!withIdb || !self.indexedDB || !indexedDB.databases) return out;
  const plain = (v, depth) => {
    if (v === null || typeof v === 'string' || typeof v === 'boolean') return true;
    if (typeof v === 'number') return Number.isFinite(v) && !Object.is(v, -0);
    if (depth > 40 || typeof v !== 'object') return false;
    if (Array.isArray(v)) return v.every((x) => plain(x, depth + 1));
    const proto = Object.getPrototypeOf(v);
    if ((proto !== Object.prototype && proto !== null) || Object.hasOwn(v, '$t')) return false;
    return Object.values(v).every((x) => plain(x, depth + 1));
  };
  class Skip extends Error {}
  const b64 = (u8) => { let s = ''; for (let i = 0; i < u8.length; i += 0x8000) s += String.fromCharCode.apply(null, u8.subarray(i, i + 0x8000)); return btoa(s); };
  const VIEWS = 'Int8Array Uint8Array Uint8ClampedArray Int16Array Uint16Array Int32Array Uint32Array Float32Array Float64Array BigInt64Array BigUint64Array DataView'.split(' ');
  const enc = async (v, seen) => {
    if (plain(v, 0)) return v;
    if (typeof v === 'number') return {$t: 'num', v: Object.is(v, -0) ? '-0' : String(v)};
    if (v === undefined) return {$t: 'undef'};
    if (typeof v === 'bigint') return {$t: 'big', v: String(v)};
    if (typeof v !== 'object') throw new Skip(typeof v);
    if (seen.has(v)) throw new Skip('a value that contains itself');
    seen.add(v);
    try {
      const tag = Object.prototype.toString.call(v).slice(8, -1);
      if (Array.isArray(v)) { const a = []; for (const x of v) a.push(await enc(x, seen)); return a; }
      if (tag === 'Date') return {$t: 'date', v: String(v.getTime())};
      if (tag === 'RegExp') return {$t: 're', s: v.source, f: v.flags};
      if (tag === 'ArrayBuffer') return {$t: 'ab', b: b64(new Uint8Array(v))};
      if (VIEWS.includes(tag)) return {$t: 'ta', k: tag, b: b64(new Uint8Array(v.buffer, v.byteOffset, v.byteLength))};
      if (tag === 'Map') { const m = []; for (const [k, x] of v) m.push([await enc(k, seen), await enc(x, seen)]); return {$t: 'map', v: m}; }
      if (tag === 'Set') { const a = []; for (const x of v) a.push(await enc(x, seen)); return {$t: 'set', v: a}; }
      if (tag === 'Number' || tag === 'String' || tag === 'Boolean') return {$t: 'box', v: await enc(v.valueOf(), seen)};
      if (tag === 'Blob' || tag === 'File') {
        const o = {$t: 'blob', type: v.type, b: b64(new Uint8Array(await v.arrayBuffer()))};
        if (tag === 'File') { o.name = v.name; o.lm = v.lastModified; }
        return o;
      }
      if (tag === 'CryptoKey') {
        if (!v.extractable) throw new Skip("encryption keys the browser won't let be copied");
        const a = v.algorithm, alg = {name: a.name};
        if (a.hash) alg.hash = a.hash.name || a.hash;
        if (a.namedCurve) alg.namedCurve = a.namedCurve;
        if (a.name === 'HMAC' && a.length) alg.length = a.length;
        return {$t: 'key', jwk: await crypto.subtle.exportKey('jwk', v), alg, use: v.usages};
      }
      const proto = Object.getPrototypeOf(v);
      if (proto !== Object.prototype && proto !== null) throw new Skip(tag + ' values');
      const o = {};
      for (const k of Object.keys(v)) o[k] = await enc(v[k], seen);
      return Object.hasOwn(o, '$t') ? {$t: 'obj', v: o} : o;
    } finally { seen.delete(v); }
  };
  const req = (r) => new Promise((ok, fail) => { r.onsuccess = () => ok(r.result); r.onerror = () => fail(r.error); });
  const DB_LIMIT = 25 * 1024 * 1024, LIMIT = 60 * 1024 * 1024;
  let total = 0;
  const dump = async () => {
    const dbs = [], skipped = [];
    for (const info of await indexedDB.databases()) {
      if (!info.name || !info.version) continue;
      const db = await req(indexedDB.open(info.name));
      try {
        const names = [...db.objectStoreNames];
        const raw = [];
        if (names.length) {  // read everything in one transaction, then encode (awaiting would end it)
          const tx = db.transaction(names, 'readonly');
          for (const name of names) {
            const st = tx.objectStore(name);
            const s = {name, autoIncrement: st.autoIncrement, indexes: [...st.indexNames].map((n) => {
              const ix = st.index(n), d = {name: ix.name, unique: ix.unique, multiEntry: ix.multiEntry};
              if (Array.isArray(ix.keyPath)) d.keyPathArray = ix.keyPath; else d.keyPath = ix.keyPath;
              return d; })};
            if (Array.isArray(st.keyPath)) s.keyPathArray = st.keyPath; else if (st.keyPath !== null) s.keyPath = st.keyPath;
            raw.push([s, st.keyPath === null, ...(await Promise.all([req(st.getAllKeys()), req(st.getAll())]))]);
          }
        }
        let size = 0;
        const stores = [];
        for (const [s, outOfLine, keys, values] of raw) {
          const records = [];
          for (let i = 0; i < keys.length; i++) {
            const rec = {value: await enc(values[i], new Set())};
            if (outOfLine) rec.key = await enc(keys[i], new Set());
            size += JSON.stringify(rec).length;
            if (size > DB_LIMIT || total + size > LIMIT) throw new Skip('too big to copy (over 25 MB)');
            records.push(rec);
          }
          stores.push({...s, records});
        }
        total += size;
        dbs.push({name: info.name, version: info.version, stores});
      } catch (e) {
        if (!(e instanceof Skip)) throw e;
        skipped.push({name: info.name, why: e.message});
      } finally { db.close(); }
    }
    return {dbs, skipped};
  };
  try {
    out[3] = await Promise.race([dump(), new Promise((_, fail) => setTimeout(() => fail(new Error('slow')), 20000))]);
  } catch (e) {}
  return out;
}
"""

# Runs in a page of the site: writes saved databases (from STORAGE_JS) back. Returns the problems.
# Used on a blank page of the site before the agent's first visit, and on an open tab after the
# user logs in again (it then replaces the records of those stores).
RESTORE_IDB_JS = r"""
async (dbs) => {
  const bytes = (b) => Uint8Array.from(atob(b), (c) => c.charCodeAt(0));
  const dec = async (v) => {
    if (v === null || typeof v !== 'object') return v;
    if (Array.isArray(v)) { const a = []; for (const x of v) a.push(await dec(x)); return a; }
    const obj = async (src) => { const o = {}; for (const k of Object.keys(src)) o[k] = await dec(src[k]); return o; };
    switch (v.$t) {
      case undefined: return obj(v);
      case 'obj': return obj(v.v);
      case 'num': return Number(v.v);
      case 'undef': return undefined;
      case 'big': return BigInt(v.v);
      case 'date': return new Date(Number(v.v));
      case 're': return new RegExp(v.s, v.f);
      case 'ab': return bytes(v.b).buffer;
      case 'ta': { const u = bytes(v.b); return v.k === 'DataView' ? new DataView(u.buffer) : new self[v.k](u.buffer); }
      case 'map': { const m = new Map(); for (const [k, x] of v.v) m.set(await dec(k), await dec(x)); return m; }
      case 'set': { const s = new Set(); for (const x of v.v) s.add(await dec(x)); return s; }
      case 'box': return Object(await dec(v.v));
      case 'blob': return v.name !== undefined ? new File([bytes(v.b)], v.name, {type: v.type, lastModified: v.lm})
                                               : new Blob([bytes(v.b)], {type: v.type});
      case 'key': return crypto.subtle.importKey('jwk', v.jwk, v.alg, true, v.use);
      default: throw new Error('unknown saved value ' + v.$t);
    }
  };
  const req = (r) => new Promise((ok, fail) => { r.onsuccess = () => ok(r.result); r.onerror = () => fail(r.error); });
  const problems = [];
  for (const db of dbs) {
    try {
      const stores = [];
      for (const st of db.stores) {
        const recs = [];
        for (const r of st.records) recs.push([await dec(r.value), 'key' in r, 'key' in r ? await dec(r.key) : undefined]);
        stores.push([st, recs]);
      }
      const open = indexedDB.open(db.name, db.version);
      open.onupgradeneeded = () => {
        const d = open.result;
        for (const st of db.stores) {
          if (d.objectStoreNames.contains(st.name)) continue;
          const os = d.createObjectStore(st.name, {autoIncrement: !!st.autoIncrement, keyPath: st.keyPathArray ?? st.keyPath ?? null});
          for (const ix of st.indexes || []) os.createIndex(ix.name, ix.keyPathArray ?? ix.keyPath, {unique: !!ix.unique, multiEntry: !!ix.multiEntry});
        }
      };
      let d;
      try { d = await req(open); } catch (e) {
        if (!e || e.name !== 'VersionError') throw e;
        d = await req(indexedDB.open(db.name));  // the site already upgraded it: fill the stores it has
      }
      try {
        const names = stores.map(([st]) => st.name).filter((n) => d.objectStoreNames.contains(n));
        if (names.length) {
          const tx = d.transaction(names, 'readwrite');
          const done = new Promise((ok, fail) => { tx.oncomplete = ok; tx.onerror = () => fail(tx.error); tx.onabort = () => fail(tx.error); });
          for (const [st, recs] of stores) {
            if (!names.includes(st.name)) continue;
            const os = tx.objectStore(st.name);
            os.clear();
            for (const [value, hasKey, key] of recs) hasKey ? os.put(value, key) : os.put(value);
          }
          await done;
        }
      } finally { d.close(); }
    } catch (e) {
      problems.push(db.name + ': ' + ((e && e.message) || e));
    }
  }
  return problems;
}
"""

# Extra keys kept next to Playwright's state in the vault. Never part of meta: list_profiles shows meta.
EXTRA_KEYS = ("session_storage", "indexed_db", "http_credentials", "ignore_https_errors")


def split(state: dict | None) -> tuple[dict | None, dict]:
    """Saved state -> (what Playwright accepts as storage_state, the extras).
    IndexedDB is restored by Assertify itself (RESTORE_IDB_JS), so it moves to extras["indexed_db"].
    Logins saved by older versions may hold Playwright's own encoding ("valueEncoded"); only those
    stay with Playwright, which knows how to read them."""
    if not state:
        return None, {}
    extras = {k: state[k] for k in EXTRA_KEYS if k in state}
    idb = dict(extras.get("indexed_db") or {})
    origins = []
    for o in state.get("origins", []):
        dbs = o.get("indexedDB")
        if dbs and not _playwright_encoded(dbs):
            idb.setdefault(o["origin"], dbs)
            o = {k: v for k, v in o.items() if k != "indexedDB"}
        elif dbs and o["origin"] in idb:
            o = {k: v for k, v in o.items() if k != "indexedDB"}
        origins.append(o)
    if idb:
        extras["indexed_db"] = idb
    return {"cookies": state.get("cookies", []), "origins": origins}, extras


def _playwright_encoded(dbs: list) -> bool:
    return any(
        "valueEncoded" in r or "keyEncoded" in r for db in dbs for st in db.get("stores", []) for r in st["records"]
    )


def merge_idb(old: list | None, dump: dict) -> list:
    """A new IndexedDB dump of one site, keeping the earlier copy of any database it had to skip."""
    skipped = {s["name"] for s in dump.get("skipped", [])}
    dbs = clean_idb(dump.get("dbs", []))
    names = {d["name"] for d in dbs}
    return dbs + [d for d in old or [] if d["name"] in skipped and d["name"] not in names]


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


def summary(state: dict) -> dict:
    """How much a saved login holds besides cookies, for list_profiles (counts only, never values)."""
    origins = state.get("origins", [])
    out = {
        "local_storage_items": sum(len(o.get("localStorage", [])) for o in origins),
        "indexed_db_databases": sum(len(o.get("indexedDB", [])) for o in origins)
        + sum(len(v) for v in (state.get("indexed_db") or {}).values()),
        "session_storage_items": sum(len(v) for v in (state.get("session_storage") or {}).values()),
    }
    return {k: v for k, v in out.items() if v}


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
