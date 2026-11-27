"""P6 cut-overs: traqfreq's own library database (``TRAQFREQ_DATA_DIR/library.sqlite``), docs/specs/t29-cutovers.md.

Each cut-over owns whole jimbo-dj tables (and some ``meta`` keys by name). ``copy`` copies them once from
jimbo-dj's database, read-only, with jimbo-dj's own ``CREATE`` statements, and checks the copy by count and
row by row in the same transaction; any failed check rolls it all back. From then on traqfreq reads its copy
(``reader``: the legacy connection with ``library.sqlite`` attached and a TEMP VIEW per owned table) and, from
the session that builds the cut-over's writer, writes it. ``rollback`` puts the tables aside and reads go back
to jimbo-dj's copy. Every copy, refusal and rollback goes to ``cutover_log`` with its reason.

Nothing here writes to jimbo-dj's database: it is only ever opened or attached with ``mode=ro``
(``legacy.connect`` / ``legacy.attach``).
"""

from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

from . import legacy

FILE = "library.sqlite"
SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS cutovers (
    name TEXT PRIMARY KEY, state TEXT NOT NULL, copied_at REAL NOT NULL, stamp TEXT NOT NULL, counts TEXT NOT NULL,
    note TEXT
);
CREATE TABLE IF NOT EXISTS cutover_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT, at REAL NOT NULL, name TEXT NOT NULL, action TEXT NOT NULL,
    reason TEXT NOT NULL, detail TEXT NOT NULL
);
"""
OWNED, ROLLED_BACK = "owned", "rolled_back"
TRAQFREQ_TABLES = frozenset({"meta", "cutovers", "cutover_log"})


@dataclass(frozen=True)
class Cutover:
    title: str
    tables: tuple[str, ...]  # must be in jimbo-dj's database
    optional: tuple[str, ...] = ()  # copied when present (a table jimbo-dj only makes once it's used)
    meta: tuple[str, ...] = ()  # meta keys this cut-over owns


# The registry. Later sessions add theirs (analysis T35, playlists T37, tags T40) when their writer is built,
# so nothing can be copied before traqfreq can write it.
CUTOVERS: dict[str, Cutover] = {
    "plex": Cutover(
        title="Plex scan and play log",
        tables=("tracks", "albums", "artists", "listens", "listen_matches", "history_imports",
                "mb_artists", "mb_releases"),
        optional=("mb_artist_names",),
        meta=("last_sync", "server", "history_version", "match_version", "plex_history_version", "history_tz",
              "applemusic_utc"),
    ),
}


class CutoverError(RuntimeError):
    """A copy or rollback refused, with the reason (also in cutover_log)."""


def path(data_dir: Path) -> Path:
    return Path(data_dir) / FILE


def connect(data_dir: Path) -> sqlite3.Connection:
    """traqfreq's library database, writable (it's traqfreq's own file). WAL, no memory-mapped reads (as jimbo-dj's
    db.connect), autocommit so the copy controls its own transaction."""
    p = path(data_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(f"file:{quote(str(p.resolve()))}", uri=True, timeout=30, check_same_thread=False,
                           isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA mmap_size = 0")
    conn.executescript(SCHEMA)
    return conn


def _log(conn: sqlite3.Connection, name: str, action: str, reason: str, detail: dict) -> None:
    conn.execute("INSERT INTO cutover_log (at, name, action, reason, detail) VALUES (?, ?, ?, ?, ?)",
                 (time.time(), name, action, reason, json.dumps(detail, sort_keys=True)))


def _tables_in(conn: sqlite3.Connection, schema: str) -> set[str]:
    return {r[0] for r in conn.execute(f"SELECT name FROM {schema}.sqlite_master WHERE type = 'table'")}


def owned(data_dir: Path) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """(tables, meta keys) of every owned cut-over, as recorded in library.sqlite. Empty when there's no file.
    Opened read-only: reading never creates the file."""
    p = path(data_dir)
    if not p.is_file():
        return (), ()
    conn = sqlite3.connect(f"file:{quote(str(p.resolve()))}?mode=ro", uri=True)
    try:
        if "cutovers" not in _tables_in(conn, "main"):
            return (), ()
        have = _tables_in(conn, "main")
        tables: list[str] = []
        keys: list[str] = []
        for (name,) in conn.execute("SELECT name FROM cutovers WHERE state = ? ORDER BY name", (OWNED,)):
            c = CUTOVERS.get(name)
            if c is None:
                continue
            tables += [t for t in c.tables + c.optional if t in have]
            keys += list(c.meta)
        return tuple(tables), tuple(keys)
    finally:
        conn.close()


def reader(legacy_db: Path, data_dir: Path) -> sqlite3.Connection:
    """The reading connection every page uses: jimbo-dj's database read-only, with traqfreq's copy of every
    owned table in front of it (legacy.connect's ``own``). Before any copy it is exactly legacy.connect()."""
    tables, keys = owned(data_dir)
    if not tables and not keys:
        return legacy.connect(legacy_db)
    return legacy.connect(legacy_db, own=(path(data_dir), tables, keys))


def _measure_sql(sql: str, table: str, schema: str) -> str:
    return sql.replace(f"FROM {table}", f"FROM {schema}.{table}")


def _stamp(conn: sqlite3.Connection, schema: str, tables: list[str]) -> dict:
    """What a copy was taken from (or what jimbo-dj's side holds now): each table's rows, the highest listen id,
    jimbo-dj's last sync and its newest history import."""
    def one(sql):
        r = conn.execute(sql).fetchone()
        return r[0] if r else None

    have = _tables_in(conn, schema)
    out: dict = {"rows": {t: one(f'SELECT COUNT(*) FROM {schema}."{t}"') for t in tables if t in have}}
    if "listens" in have:
        out["max_listen_id"] = one(f"SELECT MAX(id) FROM {schema}.listens")
    if "history_imports" in have:
        out["last_import_at"] = one(f"SELECT MAX(at) FROM {schema}.history_imports")
    if "meta" in have:
        out["last_sync"] = one(f"SELECT value FROM {schema}.meta WHERE key = 'last_sync'")
    return out


def copy(legacy_db: Path, data_dir: Path, name: str, reason: str) -> dict:
    """The one-time copy of cut-over ``name`` into library.sqlite, checked before it commits:
    - per table, the same row count and no row different either way (EXCEPT both ways);
    - jimbo-dj's numbers (legacy.MEASURES) the same on the copy as on jimbo-dj's side;
    - every owned meta key the same.
    Read from jimbo-dj in one transaction (one snapshot). Refused when already owned. Returns the record."""
    if name not in CUTOVERS:
        raise CutoverError(f"no cut-over named {name!r} (known: {', '.join(sorted(CUTOVERS))})")
    if not reason.strip():
        raise CutoverError("a reason is required")
    c = CUTOVERS[name]
    conn = connect(data_dir)
    try:
        row = conn.execute("SELECT state FROM cutovers WHERE name = ?", (name,)).fetchone()
        if row and row["state"] == OWNED:
            msg = f"{name} is already owned by traqfreq: a second copy would overwrite traqfreq's own writes"
            _log(conn, name, "refused", reason, {"why": msg})
            raise CutoverError(msg)
        legacy.attach(conn, legacy_db, "legacy")
        t0 = time.time()
        problems: list[str] = []
        conn.execute("BEGIN IMMEDIATE")
        try:
            in_legacy = _tables_in(conn, "legacy")
            in_own = _tables_in(conn, "main")
            missing = [t for t in c.tables if t not in in_legacy]
            if missing:
                raise CutoverError(f"not in jimbo-dj's database: {', '.join(missing)}")
            tables = list(c.tables) + [t for t in c.optional if t in in_legacy]
            clash = [t for t in tables if t in in_own or t in TRAQFREQ_TABLES]
            if clash:
                raise CutoverError(f"already in library.sqlite: {', '.join(clash)}")
            counts: dict[str, dict] = {}
            for t in tables:
                sql = conn.execute("SELECT sql FROM legacy.sqlite_master WHERE type = 'table' AND name = ?",
                                   (t,)).fetchone()[0]
                conn.execute(sql)  # unqualified CREATE: main, i.e. library.sqlite
                for (isql,) in conn.execute("SELECT sql FROM legacy.sqlite_master WHERE type = 'index' "
                                            "AND tbl_name = ? AND sql IS NOT NULL", (t,)).fetchall():
                    conn.execute(isql)
                conn.execute(f'INSERT INTO main."{t}" SELECT * FROM legacy."{t}"')
                n_legacy = conn.execute(f'SELECT COUNT(*) FROM legacy."{t}"').fetchone()[0]
                n_own = conn.execute(f'SELECT COUNT(*) FROM main."{t}"').fetchone()[0]
                only_legacy = conn.execute(
                    f'SELECT COUNT(*) FROM (SELECT * FROM legacy."{t}" EXCEPT SELECT * FROM main."{t}")').fetchone()[0]
                only_own = conn.execute(
                    f'SELECT COUNT(*) FROM (SELECT * FROM main."{t}" EXCEPT SELECT * FROM legacy."{t}")').fetchone()[0]
                counts[t] = {"jimbodj": n_legacy, "traqfreq": n_own, "only_jimbodj": only_legacy,
                             "only_traqfreq": only_own}
                if n_legacy != n_own or only_legacy or only_own:
                    problems.append(f"{t}: {n_legacy} rows in jimbo-dj, {n_own} copied, "
                                    f"{only_legacy} only in jimbo-dj, {only_own} only in the copy")
            meta: dict[str, dict] = {}
            if "meta" in in_legacy:
                for k in c.meta:
                    r = conn.execute("SELECT value FROM legacy.meta WHERE key = ?", (k,)).fetchone()
                    if r is not None:
                        conn.execute("INSERT INTO main.meta (key, value) VALUES (?, ?) "
                                     "ON CONFLICT(key) DO UPDATE SET value = excluded.value", (k, r[0]))
                    mine = conn.execute("SELECT value FROM main.meta WHERE key = ?", (k,)).fetchone()
                    meta[k] = {"jimbodj": r[0] if r else None, "traqfreq": mine[0] if mine else None}
                    if (r[0] if r else None) != (mine[0] if mine else None):
                        problems.append(f"meta {k}: differs")
            measures: dict[str, dict] = {}
            for mid, table, sql, _stored in legacy.MEASURES:
                if table not in tables:
                    continue
                a = conn.execute(_measure_sql(sql, table, "legacy")).fetchone()[0]
                b = conn.execute(_measure_sql(sql, table, "main")).fetchone()[0]
                measures[mid] = {"jimbodj": a, "traqfreq": b}
                if a != b:
                    problems.append(f"{mid}: jimbo-dj counts {a}, the copy {b}")
            stamp = _stamp(conn, "legacy", tables)
            check = {"tables": counts, "meta": meta, "measures": measures}
            if problems:
                raise CutoverError("the copy doesn't match jimbo-dj: " + "; ".join(problems))
            now = time.time()
            conn.execute("INSERT INTO cutovers (name, state, copied_at, stamp, counts, note) VALUES (?, ?, ?, ?, ?, ?) "
                         "ON CONFLICT(name) DO UPDATE SET state = excluded.state, copied_at = excluded.copied_at, "
                         "stamp = excluded.stamp, counts = excluded.counts, note = excluded.note",
                         (name, OWNED, now, json.dumps(stamp, sort_keys=True), json.dumps(check, sort_keys=True),
                          reason))
            _log(conn, name, "copied", reason, {"tables": tables, "check": check, "stamp": stamp,
                                                 "seconds": round(time.time() - t0, 2),
                                                 "undo": f"traqfreq-cutover rollback {name} --reason …"})
            conn.execute("COMMIT")
        except BaseException as e:
            conn.execute("ROLLBACK")
            why = str(e) if isinstance(e, CutoverError) else f"{type(e).__name__}: {e}"
            _log(conn, name, "refused", reason, {"why": why})
            if isinstance(e, CutoverError):
                raise
            raise CutoverError(why) from e
        conn.execute("DETACH DATABASE legacy")
    finally:
        conn.close()
    _check_reader(legacy_db, data_dir, name, check)
    return record(data_dir, name)


def _check_reader(legacy_db: Path, data_dir: Path, name: str, check: dict) -> None:
    """After the commit: the reading connection must show the copy, not jimbo-dj's side (which may already have
    moved on, so the copy's own numbers are the yardstick). If it doesn't, the cut-over is rolled back."""
    conn = reader(legacy_db, data_dir)
    try:
        bad = []
        for t, n in check["tables"].items():
            got = conn.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
            if got != n["traqfreq"]:
                bad.append(f"{t}: the reading connection sees {got}, the copy has {n['traqfreq']}")
        for mid, table, sql, _stored in legacy.MEASURES:
            if mid in check["measures"]:
                got = conn.execute(sql).fetchone()[0]
                if got != check["measures"][mid]["traqfreq"]:
                    bad.append(f"{mid}: the reading connection counts {got}")
    finally:
        conn.close()
    if bad:
        rollback(data_dir, name, "the reading connection didn't show the copy: " + "; ".join(bad))
        raise CutoverError("rolled back: " + "; ".join(bad))


def rollback(data_dir: Path, name: str, reason: str) -> dict:
    """Hand cut-over ``name`` back to jimbo-dj's copy: its tables renamed ``<table>__rolled_back_<unix time>``
    (their indexes dropped, so a later copy can make them again), its meta keys removed (their values kept in
    the log), state ``rolled_back``. Reads go back to jimbo-dj's copy at once; nothing traqfreq wrote is lost."""
    if not reason.strip():
        raise CutoverError("a reason is required")
    conn = connect(data_dir)
    try:
        row = conn.execute("SELECT state FROM cutovers WHERE name = ?", (name,)).fetchone()
        if not row or row["state"] != OWNED:
            msg = f"{name} isn't owned by traqfreq, so there's nothing to roll back"
            _log(conn, name, "refused", reason, {"why": msg})
            raise CutoverError(msg)
        c = CUTOVERS[name]
        suffix = f"__rolled_back_{int(time.time())}"
        conn.execute("BEGIN IMMEDIATE")
        try:
            have = _tables_in(conn, "main")
            moved = {}
            for t in c.tables + c.optional:
                if t not in have:
                    continue
                for (idx,) in conn.execute("SELECT name FROM sqlite_master WHERE type = 'index' AND tbl_name = ? "
                                           "AND sql IS NOT NULL", (t,)).fetchall():
                    conn.execute(f'DROP INDEX "{idx}"')
                conn.execute(f'ALTER TABLE "{t}" RENAME TO "{t}{suffix}"')
                moved[t] = t + suffix
            keys = {k: v for k, v in conn.execute(
                f"SELECT key, value FROM meta WHERE key IN ({','.join('?' * len(c.meta))})", c.meta)} if c.meta else {}
            if keys:
                conn.execute(f"DELETE FROM meta WHERE key IN ({','.join('?' * len(keys))})", tuple(keys))
            conn.execute("UPDATE cutovers SET state = ?, note = ? WHERE name = ?", (ROLLED_BACK, reason, name))
            _log(conn, name, "rolled_back", reason, {"tables": moved, "meta": keys,
                                                      "undo": f"traqfreq-cutover copy {name} --reason …"})
            conn.execute("COMMIT")
        except BaseException:
            conn.execute("ROLLBACK")
            raise
    finally:
        conn.close()
    return record(data_dir, name)


def record(data_dir: Path, name: str) -> dict:
    """One cut-over: its registry entry, state and copy record (or ``state: not_copied``)."""
    c = CUTOVERS[name]
    out = {"name": name, "title": c.title, "tables": list(c.tables), "optional": list(c.optional),
           "meta": list(c.meta), "state": "not_copied", "copied_at": None, "stamp": None, "check": None, "note": None}
    if not path(data_dir).is_file():
        return out
    conn = connect(data_dir)
    try:
        r = conn.execute("SELECT * FROM cutovers WHERE name = ?", (name,)).fetchone()
    finally:
        conn.close()
    if r:
        out.update(state=r["state"], copied_at=r["copied_at"], stamp=json.loads(r["stamp"]),
                   check=json.loads(r["counts"]), note=r["note"])
    return out


def status(data_dir: Path, log_limit: int = 20) -> dict:
    """Every cut-over's record and the newest log entries."""
    log: list[dict] = []
    if path(data_dir).is_file():
        conn = connect(data_dir)
        try:
            log = [{"id": r["id"], "at": r["at"], "name": r["name"], "action": r["action"], "reason": r["reason"],
                    "detail": json.loads(r["detail"])}
                   for r in conn.execute("SELECT * FROM cutover_log ORDER BY id DESC LIMIT ?", (log_limit,))]
        finally:
            conn.close()
    return {"file": str(path(data_dir)), "cutovers": [record(data_dir, n) for n in CUTOVERS], "log": log}


def main(argv: list[str] | None = None) -> int:
    """``traqfreq-cutover status | copy <name> --reason … | rollback <name> --reason …``. Uses TRAQFREQ_DATA_DIR
    and TRAQFREQ_LEGACY_DB like the app. Run on the mini at deploy, never against real data in tests."""
    import argparse

    from .settings import Settings

    ap = argparse.ArgumentParser(prog="traqfreq-cutover", description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status")
    for cmd in ("copy", "rollback"):
        p = sub.add_parser(cmd)
        p.add_argument("name", choices=sorted(CUTOVERS))
        p.add_argument("--reason", required=True)
    args = ap.parse_args(argv)
    s = Settings.from_env()
    try:
        if args.cmd == "status":
            out = status(s.data_dir)
        elif args.cmd == "copy":
            if s.legacy_db is None:
                raise CutoverError("TRAQFREQ_LEGACY_DB is not set")
            out = copy(s.legacy_db, s.data_dir, args.name, args.reason)
        else:
            out = rollback(s.data_dir, args.name, args.reason)
    except CutoverError as e:
        print(f"refused: {e}")
        return 1
    print(json.dumps(out, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
