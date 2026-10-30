"""Sharing one project between several users through a synced SharePoint folder, without a server.

Layout of the shared folder (normally `<program folder>/shared`, synced by OneDrive like the rest of the library):

    shared/users/<writer>.json                  who each writer is: name, role, id slot, last seen
    shared/journal/<writer>/<YYYY-MM>.jsonl     that writer's changes, one JSON line each, append-only

A writer is one user on one PC (`jane.citizen@epec.com.au@LAPTOP-7`). Each writer appends only to its own files,
so OneDrive never sees two PCs editing the same file. Every copy of PMT publishes its own change log (export) and
reads everyone else's (import), then rebuilds the touched rows from the full history of each row:

* last writer wins per column, ordered by the hybrid clock in changelog.py
* a delete is final (ids are never reused, see db.ID_SLOT)
* changes that arrive before the row they change are kept and applied when the row arrives

Nothing here talks to Microsoft directly: OneDrive does the transport. Keep the PMT folder "Always keep on this
device" so the journals are local files.
"""
import json
import os
import sqlite3
import threading
import time
import zlib
from datetime import datetime, timezone
from pathlib import Path

from . import VERSION, changelog, db, identity

SYNC_EVERY = 15          # seconds between background sync rounds
HEARTBEAT_EVERY = 300    # seconds between "last seen" updates in users/<writer>.json
MAX_SLOT = 4095

_lock = threading.RLock()
_wake = threading.Event()
_stop = threading.Event()
_thread = None
status = dict(mode="local", writer=None, slot=0, last_export=None, last_import=None, exported=0, imported=0,
              error=None, remote_seq=0, recent=[], skipped_tables=[])


def enabled():
    return db.SHARED_DIR is not None


def writer_id():
    return f"{identity.slug(identity.current()['upn'])}@{identity.device()}"


def _dirs():
    root = db.SHARED_DIR
    return root / "journal", root / "users"


def _state(con, key, default=None):
    r = con.execute("SELECT value FROM sync_state WHERE key=?", (key,)).fetchone()
    return r[0] if r else default


def _set_state(con, key, value):
    con.execute("INSERT INTO sync_state(key, value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, str(value)))


# ---------------------------------------------------------------------------------------------------------------
# People
# ---------------------------------------------------------------------------------------------------------------
def _read_json(p):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def writers():
    """Everyone who has used this shared folder: {writer: profile}."""
    if not enabled():
        return {}
    _, users = _dirs()
    out = {}
    for f in sorted(users.glob("*.json")):
        d = _read_json(f)
        if d and d.get("writer"):
            out[d["writer"]] = d
    return out


def me(con=None):
    """The current user with their role."""
    u = dict(identity.current())
    u["writer"] = writer_id()
    own = con or db.connect()
    try:
        u["role"] = _state(own, "role:" + u["upn"], "")
        nm, ent = _state(own, "name:" + u["upn"], ""), _state(own, "entity:" + u["upn"], "")
        if nm or ent:
            u.update(identity.apply_profile(nm or None, ent or None))
        u["entities"] = identity.ENTITIES
        u["prefs"] = get_prefs(own, u["upn"])
    finally:
        if con is None:
            own.close()
    return u


def get_prefs(con, upn=None):
    """This person's view defaults (Settings > Your defaults): {key: value}. Kept on this PC, not shared."""
    try:
        return json.loads(_state(con, "prefs:" + (upn or identity.current()["upn"]), "{}") or "{}")
    except ValueError:
        return {}


def set_prefs(con, prefs):
    """Replace this person's view defaults. Only plain values are kept (numbers, text, true/false)."""
    clean = {str(k)[:60]: v for k, v in (prefs or {}).items() if isinstance(v, (str, int, float, bool)) or v is None}
    _set_state(con, "prefs:" + identity.current()["upn"], json.dumps(clean))
    con.commit()
    return clean


def set_role(con, role, name=None, entity=None):
    upn = identity.current()["upn"]
    if role is not None:
        _set_state(con, "role:" + upn, (role or "").strip()[:60])
    if name is not None:
        _set_state(con, "name:" + upn, name.strip()[:80])
    if entity is not None:
        _set_state(con, "entity:" + upn, entity.strip()[:80])
    identity.apply_profile(name, entity)
    if enabled():
        _heartbeat(con, force=True)


def people(con):
    """upn -> {name, role} for everyone known (shared folder profiles plus anyone seen in the change log)."""
    out = {}
    for r in con.execute("SELECT user_upn, MAX(user_name) FROM change_log WHERE user_upn IS NOT NULL GROUP BY user_upn"):
        out[r[0]] = dict(upn=r[0], name=r[1], role=_state(con, "role:" + r[0], ""))
    for w in writers().values():
        if w.get("upn"):
            out.setdefault(w["upn"], dict(upn=w["upn"], name=w.get("name"), role=""))
            out[w["upn"]]["name"] = w.get("name") or out[w["upn"]]["name"]
            if w.get("role"):
                out[w["upn"]]["role"] = w["role"]
    m = me(con)
    out.setdefault(m["upn"], dict(upn=m["upn"], name=m["name"], role=""))
    if m.get("role"):
        out[m["upn"]]["role"] = m["role"]
    return out


_last_beat = 0


def _heartbeat(con, force=False):
    global _last_beat
    if not force and time.time() - _last_beat < HEARTBEAT_EVERY:
        return
    _, users = _dirs()
    u = identity.current()
    prof = dict(writer=writer_id(), upn=u["upn"], name=u["name"], source=u["source"], device=identity.device(),
                role=_state(con, "role:" + u["upn"], ""), slot=int(_state(con, "slot", 0) or 0), app_version=VERSION,
                last_seen=datetime.now(timezone.utc).isoformat(timespec="seconds"))
    old = _read_json(users / f"{prof['writer']}.json") or {}
    prof["first_seen"] = old.get("first_seen") or prof["last_seen"]
    tmp = users / f".{prof['writer']}.tmp"
    tmp.write_text(json.dumps(prof, indent=1), encoding="utf-8")
    os.replace(tmp, users / f"{prof['writer']}.json")
    _last_beat = time.time()


def _claim_slot(con):
    """A slot of its own for this writer, so row ids never collide (db.ID_SLOT)."""
    s = int(_state(con, "slot", 0) or 0)
    if s:
        return s
    w = writer_id()
    taken = {int(d.get("slot") or 0): k for k, d in writers().items() if k != w}
    s = zlib.crc32(w.encode()) % MAX_SLOT + 1
    while s in taken:
        s = s % MAX_SLOT + 1
    _set_state(con, "slot", s)
    return s


# ---------------------------------------------------------------------------------------------------------------
# Start / stop
# ---------------------------------------------------------------------------------------------------------------
def start(background=True):
    """Called at app start-up after db.init_db()."""
    if not enabled():
        status["mode"] = "local"
        return
    journal, users = _dirs()
    journal.mkdir(parents=True, exist_ok=True)
    users.mkdir(parents=True, exist_ok=True)
    (journal / writer_id()).mkdir(exist_ok=True)
    con = db.connect()
    try:
        slot = _claim_slot(con)
        con.commit()
        db.ID_SLOT = slot
        status.update(mode="shared", writer=writer_id(), slot=slot, folder=str(db.SHARED_DIR))
        _heartbeat(con, force=True)
    finally:
        con.close()
    sync_now()
    if background:
        global _thread
        _stop.clear()
        _thread = threading.Thread(target=_loop, name="pmt-sync", daemon=True)
        _thread.start()


def stop():
    _stop.set()
    _wake.set()


def poke():
    """Ask for a sync soon (after a local edit)."""
    _wake.set()


def _loop():
    while not _stop.is_set():
        _wake.wait(SYNC_EVERY)
        _wake.clear()
        if _stop.is_set():
            break
        time.sleep(1.0)  # let a burst of edits finish
        sync_now()


def sync_now():
    if not enabled():
        return status
    with _lock:
        try:
            export()
            import_all()
            con = db.connect()
            try:
                _heartbeat(con)
            finally:
                con.close()
            status["error"] = None
        except Exception as e:  # never take the app down over sync; show it instead
            status["error"] = f"{type(e).__name__}: {e}"
    return status


# ---------------------------------------------------------------------------------------------------------------
# Export: publish my changes
# ---------------------------------------------------------------------------------------------------------------
FIELDS = ("ts", "at", "user_upn", "user_name", "via", "txn", "project_id", "tbl", "row_id", "op", "data")


def export():
    journal, _ = _dirs()
    w = writer_id()
    mine = journal / w
    mine.mkdir(parents=True, exist_ok=True)
    con = db.connect()
    n = 0
    try:
        while True:
            rows = con.execute(f"SELECT id, {', '.join(FIELDS)} FROM change_log WHERE remote=0 AND uid IS NULL ORDER BY id LIMIT 5000").fetchall()
            if not rows:
                break
            by_file = {}
            for r in rows:
                e = {k: r[k] for k in FIELDS}
                e["data"] = json.loads(r["data"]) if r["data"] else None
                e["uid"] = f"{w}:{r['id']}"
                e["v"] = VERSION
                by_file.setdefault((r["at"] or "")[:7] or "0000-00", []).append(e)
            for month, es in by_file.items():
                with open(mine / f"{month}.jsonl", "a", encoding="utf-8", newline="\n") as f:
                    for e in es:
                        f.write(json.dumps(e, separators=(",", ":"), ensure_ascii=False) + "\n")
                    f.flush()
                    os.fsync(f.fileno())
            con.executemany("UPDATE change_log SET uid=?, writer=? WHERE id=?", [(f"{w}:{r['id']}", w, r["id"]) for r in rows])
            con.commit()
            n += len(rows)
    finally:
        con.close()
    if n:
        status["exported"] += n
        status["last_export"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return n


# ---------------------------------------------------------------------------------------------------------------
# Import: read everyone else's changes and rebuild the rows they touch
# ---------------------------------------------------------------------------------------------------------------
def _read_new(con, path):
    """Complete new lines since the last read (a line still being synced by OneDrive is left for next time)."""
    key = str(path.relative_to(db.SHARED_DIR)).replace("\\", "/")
    rec = con.execute("SELECT offset FROM sync_file WHERE path=?", (key,)).fetchone()
    off = rec[0] if rec else 0
    size = path.stat().st_size
    if size < off:  # file replaced: read it again; duplicates are skipped by uid
        off = 0
    if size == off:
        return key, off, []
    with open(path, "rb") as f:
        f.seek(off)
        chunk = f.read(size - off)
    end = chunk.rfind(b"\n")
    if end < 0:
        return key, off, []
    out = []
    for line in chunk[:end].splitlines():
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except ValueError:
                continue
    return key, off + end + 1, out


def import_all():
    if not enabled():
        return 0
    journal, _ = _dirs()
    w = writer_id()
    con = db.connect(logging=False)
    con.execute("PRAGMA foreign_keys = OFF")  # rows arrive in any order; deletes are journaled row by row
    try:
        con.execute("BEGIN IMMEDIATE")
        entries, offsets = [], []
        for d in sorted(p for p in journal.iterdir() if p.is_dir() and p.name != w):
            for f in sorted(d.glob("*.jsonl")):
                key, off, es = _read_new(con, f)
                offsets.append((key, off))
                entries.extend(es)
        n = apply_entries(con, entries)
        con.executemany("INSERT INTO sync_file(path, offset) VALUES (?,?) ON CONFLICT(path) DO UPDATE SET offset=excluded.offset", offsets)
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()
    status["last_import"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return n


def apply_entries(con, entries):
    """Store new remote entries in change_log and rebuild every row they touch. Returns the number applied."""
    have = set()
    uids = [e.get("uid") for e in entries if e.get("uid")]
    for i in range(0, len(uids), 500):
        part = uids[i:i + 500]
        have.update(r[0] for r in con.execute(f"SELECT uid FROM change_log WHERE uid IN ({','.join('?' * len(part))})", part))
    fresh = []
    for e in entries:
        u = e.get("uid")
        if not u or u in have or u.startswith(writer_id() + ":"):
            continue
        have.add(u)
        fresh.append(e)
    if not fresh:
        return 0
    fresh.sort(key=lambda e: (e.get("ts") or 0, e["uid"]))
    con.executemany(
        "INSERT INTO change_log(uid, writer, remote, ts, at, user_upn, user_name, via, txn, project_id, tbl, row_id, op, data) "
        "VALUES (?,?,1,?,?,?,?,?,?,?,?,?,?,?)",
        [(e["uid"], e["uid"].rsplit(":", 1)[0], e.get("ts"), e.get("at"), e.get("user_upn"), e.get("user_name"), e.get("via"),
          e.get("txn"), e.get("project_id"), e["tbl"], e["row_id"], e["op"],
          json.dumps(e["data"], separators=(",", ":")) if e.get("data") is not None else None) for e in fresh])
    changelog.observe_ts(max(e.get("ts") or 0 for e in fresh))
    keys = list(dict.fromkeys((e["tbl"], e["row_id"]) for e in fresh))
    skipped = materialize(con, keys)
    projects = {e.get("project_id") for e in fresh if e.get("project_id")}
    for pid in projects:
        con.execute("UPDATE project SET version = COALESCE(version,0)+1 WHERE id=?", (pid,))
    # a short "what changed" summary for the screen
    by_user = {}
    for e in fresh:
        by_user.setdefault(e.get("user_name") or e.get("user_upn"), 0)
        by_user[e.get("user_name") or e.get("user_upn")] += 1
    status["imported"] += len(fresh)
    status["remote_seq"] += 1
    status["recent"] = ([dict(user=u, changes=c, at=datetime.now(timezone.utc).isoformat(timespec="seconds")) for u, c in by_user.items()] + status["recent"])[:10]
    if skipped:
        status["skipped_tables"] = sorted(set(status["skipped_tables"]) | skipped)
    return len(fresh)


def materialize(con, keys):
    """Rebuild rows from their full change history (local and remote). Returns tables this version does not know."""
    tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    cols_of = {}
    skipped = set()
    for tbl, rid in keys:
        if tbl not in tables or tbl in changelog.NOT_LOGGED:
            skipped.add(tbl)
            continue
        cols = cols_of.get(tbl) or cols_of.setdefault(tbl, [r[1] for r in con.execute(f"PRAGMA table_info({tbl})")])
        hist = con.execute("SELECT op, data FROM change_log WHERE tbl=? AND row_id=? ORDER BY ts, id", (tbl, rid)).fetchall()
        if any(op == "D" for op, _ in hist):
            con.execute(f"DELETE FROM {tbl} WHERE id=?", (rid,))
            continue
        vals, inserted = {}, False
        for op, data in hist:
            d = json.loads(data) if data else {}
            if op == "I":
                inserted = True
                vals.update(d)
            elif op == "U":
                vals.update({k: v[1] for k, v in d.items()})
        vals = {k: v for k, v in vals.items() if k in cols and k != "id"}
        exists = con.execute(f"SELECT 1 FROM {tbl} WHERE id=?", (rid,)).fetchone()
        for _ in range(4):
            try:
                if exists:
                    if vals:
                        con.execute(f"UPDATE {tbl} SET {', '.join(k + '=?' for k in vals)} WHERE id=?", [*vals.values(), rid])
                elif inserted:
                    ks = ["id", *vals]
                    con.execute(f"INSERT INTO {tbl} ({', '.join(ks)}) VALUES ({', '.join('?' * len(ks))})", [rid, *vals.values()])
                break
            except sqlite3.IntegrityError:
                if not _resolve_unique(con, tbl, rid, vals):
                    status.setdefault("conflicts", []).append(f"{tbl} {rid}: could not be merged")
                    break
    return skipped


RENAMEABLE = ("code", "ref")


def _resolve_unique(con, tbl, rid, vals):
    """Two people created the same unique key on their own copies (same CBS code, same month cell...).

    Every copy settles it the same way, so they stay identical: where the key has a code or reference, the row with
    the higher id keeps its data under a suffixed code (PL01.003~7f3a); otherwise the row with the higher id wins
    and the other is dropped. Returns True when something was changed and the write can be retried."""
    for (_, iname, unique, origin, *_r) in con.execute(f"PRAGMA index_list({tbl})").fetchall():
        if not unique or origin == "pk":
            continue
        kcols = [r[2] for r in con.execute(f"PRAGMA index_info({iname})")]
        cur = con.execute(f"SELECT * FROM {tbl} WHERE id=?", (rid,)).fetchone()
        key = [vals.get(c, cur[c] if cur else None) for c in kcols]
        other = con.execute(f"SELECT * FROM {tbl} WHERE {' AND '.join(c + ' IS ?' for c in kcols)} AND id!=?", [*key, rid]).fetchone()
        if not other:
            continue
        ren = next((c for c in kcols if c in RENAMEABLE), None)
        loser = max(rid, other["id"])
        if ren:
            if loser == rid:
                vals[ren] = f"{key[kcols.index(ren)]}~{rid % 65536:04x}"
            else:
                con.execute(f"UPDATE {tbl} SET {ren}=? WHERE id=?", (f"{other[ren]}~{other['id'] % 65536:04x}", other["id"]))
        else:
            if loser == rid:
                con.execute(f"DELETE FROM {tbl} WHERE id=?", (other["id"],))
            else:
                return False
        status.setdefault("conflicts", []).append(f"{tbl}: {'/'.join(map(str, key))} was created by two people at once")
        return True
    return False


# ---------------------------------------------------------------------------------------------------------------
# First publish of an existing database
# ---------------------------------------------------------------------------------------------------------------
def publish_existing(src_path):
    """Load an existing pmt.db (from before sharing) into this replica and journal every row, so the others get it.

    Only allowed while this replica holds no project yet, so two sets of old-style ids can never meet."""
    con = db.connect()
    try:
        if con.execute("SELECT COUNT(*) FROM project").fetchone()[0]:
            raise ValueError("This copy already holds projects. Publish an existing database only into an empty shared folder.")
    finally:
        con.close()
    src = db.connect(src_path, logging=False)
    # bring the old file up to the current schema first (migrations, no triggers needed)
    src.executescript(db.SCHEMA.read_text())
    for table, col, ddl in db.MIGRATIONS:
        have = {r[1] for r in src.execute(f"PRAGMA table_info({table})")}
        if have and col not in have:
            src.execute(f"ALTER TABLE {table} ADD COLUMN {col} {ddl}")
    src.commit()
    con = db.connect()  # logging on: each copied row becomes an "I" entry in my change log
    con.execute("PRAGMA foreign_keys = OFF")
    n = 0
    try:
        with changelog.via("Initial publish of an existing database"):
            changelog.new_txn()
            for t in changelog.data_tables(con):
                dst_cols = {r[1] for r in con.execute(f"PRAGMA table_info({t})")}
                try:
                    rows = src.execute(f"SELECT * FROM {t} ORDER BY id").fetchall()
                except Exception:
                    continue
                for r in rows:
                    d = {k: r[k] for k in r.keys() if k in dst_cols}
                    con.execute(f"INSERT INTO {t} ({', '.join(d)}) VALUES ({', '.join('?' * len(d))})", list(d.values()))
                    n += 1
        con.commit()
    finally:
        con.close()
        src.close()
    poke()
    return n
