"""Our own SQLite store (outside Clio). Built into Python, one file: data/lawmonade.db.

Tables
  shares       provider share links: what the attorney chose to share, and when the link expires
  share_views  each time a share link is opened ("has anyone in their office opened it?")
  last_opened  when each user last opened each matter ("what changed since I last opened it?")
  card_edits   a person's correction to a money card on the brief (Clio is never changed)
  card_reviews what a PERSON decided about a money card (approved / undo), with the snapshot they looked at
  audit        who did what, when. Append-only: triggers refuse UPDATE and DELETE.

Schema changes are numbered migrations (PRAGMA user_version), run once per process, so an existing
database is upgraded in place and never has to be deleted. WAL mode lets the dashboard, the provider
portal and the API read and write at the same time.
Share tokens are secrets: the audit log stores share_ref(token) (a hash), never the token.
Clio snapshots and AI answers are JSON files in data/, not here.
"""
import hashlib
import json
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone

from app.config import settings

_READY: set[str] = set()      # databases already migrated in this process


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def share_ref(token: str) -> str:
    """Stable, non-secret id for a share link, safe to store in the audit log."""
    return "share:" + hashlib.sha256(str(token).encode()).hexdigest()[:16]


def _columns(con: sqlite3.Connection, table: str) -> set[str]:
    return {r[1] for r in con.execute(f"PRAGMA table_info({table})")}


def _m1_tables(con: sqlite3.Connection) -> None:
    con.executescript("""
        CREATE TABLE IF NOT EXISTS shares (
            token TEXT PRIMARY KEY, matter_id TEXT, provider_id TEXT, provider_name TEXT,
            allowed_fields TEXT, edited_text TEXT, created_by TEXT,
            created_at TEXT, expires_at TEXT, revoked INTEGER DEFAULT 0);
        CREATE TABLE IF NOT EXISTS share_views (token TEXT, viewed_at TEXT, user_agent TEXT);
        CREATE TABLE IF NOT EXISTS last_opened (
            user_id TEXT, matter_id TEXT, opened_at TEXT, PRIMARY KEY (user_id, matter_id));
        CREATE TABLE IF NOT EXISTS card_edits (
            matter_id TEXT, card_key TEXT, value REAL, note TEXT, edited_by TEXT, edited_at TEXT,
            clio_value REAL, PRIMARY KEY (matter_id, card_key));
        CREATE TABLE IF NOT EXISTS card_reviews (
            matter_id TEXT, card_key TEXT, status TEXT, value REAL, by TEXT, at TEXT,
            PRIMARY KEY (matter_id, card_key));
        CREATE TABLE IF NOT EXISTS audit (at TEXT, action TEXT, item_id TEXT, detail TEXT);
    """)


def _m2_actor_snapshot_and_hashed_refs(con: sqlite3.Connection) -> None:
    if "actor" not in _columns(con, "audit"):
        con.execute("ALTER TABLE audit ADD COLUMN actor TEXT DEFAULT ''")
    if "snapshot" not in _columns(con, "card_reviews"):
        con.execute("ALTER TABLE card_reviews ADD COLUMN snapshot TEXT DEFAULT ''")
    for (token,) in con.execute("SELECT token FROM shares").fetchall():    # old rows held the raw token
        con.execute("UPDATE audit SET item_id = ? WHERE item_id = ?", (share_ref(token), token))
    con.execute("CREATE INDEX IF NOT EXISTS audit_item ON audit(item_id, action)")


def _m3_append_only_audit(con: sqlite3.Connection) -> None:
    con.executescript("""
        CREATE TRIGGER IF NOT EXISTS audit_no_update BEFORE UPDATE ON audit
            BEGIN SELECT RAISE(ABORT, 'the audit log is append-only'); END;
        CREATE TRIGGER IF NOT EXISTS audit_no_delete BEFORE DELETE ON audit
            BEGIN SELECT RAISE(ABORT, 'the audit log is append-only'); END;
    """)


MIGRATIONS = [_m1_tables, _m2_actor_snapshot_and_hashed_refs, _m3_append_only_audit]   # append, never edit


def migrate(con: sqlite3.Connection) -> int:
    """Run the migrations this database hasn't had yet. Returns the schema version."""
    version = con.execute("PRAGMA user_version").fetchone()[0]
    for i, step in enumerate(MIGRATIONS[version:], start=version + 1):
        with con:
            step(con)
            con.execute(f"PRAGMA user_version = {i}")
    return len(MIGRATIONS)


def _db() -> sqlite3.Connection:
    settings.db_path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(settings.db_path, timeout=10)
    con.row_factory = sqlite3.Row
    key = str(settings.db_path)
    if key not in _READY:
        con.execute("PRAGMA journal_mode=WAL")
        migrate(con)
        _READY.add(key)
    return con


def log(action: str, item_id: str, detail, con: sqlite3.Connection | None = None, actor: str = "") -> None:
    """Add one line to the append-only audit log. For share links pass share_ref(token) as item_id."""
    row = (now(), action, item_id, json.dumps(detail), actor or "")
    sql = "INSERT INTO audit (at, action, item_id, detail, actor) VALUES (?, ?, ?, ?, ?)"
    if con:
        con.execute(sql, row)
    else:
        with _db() as c:
            c.execute(sql, row)


# ---------- share links ----------
def create_share(matter_id: str, provider_id: str, provider_name: str, allowed_fields: list[str],
                 edited_text: str = "", created_by: str = "", days: int | None = None) -> str:
    token = secrets.token_urlsafe(24)
    expires = datetime.now(timezone.utc) + timedelta(days=days or settings.share_link_days)
    with _db() as con:
        con.execute("INSERT INTO shares VALUES (?,?,?,?,?,?,?,?,?,0)",
                    (token, str(matter_id), str(provider_id), provider_name, json.dumps(allowed_fields),
                     edited_text, created_by, now(), expires.isoformat(timespec="seconds")))
        log("share_created", share_ref(token), {"matter": matter_id, "provider": provider_name,
                                                "fields": allowed_fields}, con, actor=created_by)
    return token


def get_share(token: str) -> dict | None:
    """The share if it exists, is not revoked and has not expired. Else None."""
    with _db() as con:
        r = con.execute("SELECT * FROM shares WHERE token = ?", (token,)).fetchone()
    if not r or r["revoked"] or datetime.fromisoformat(r["expires_at"]) < datetime.now(timezone.utc):
        return None
    d = dict(r)
    d["allowed_fields"] = json.loads(d["allowed_fields"])
    return d


def revoke_share(token: str, by: str = "") -> None:
    with _db() as con:
        con.execute("UPDATE shares SET revoked = 1 WHERE token = ?", (token,))
        log("share_revoked", share_ref(token), "", con, actor=by)


def shares_for_matter(matter_id: str) -> list[dict]:
    with _db() as con:
        rows = con.execute("""SELECT s.*, COUNT(v.token) AS views, MAX(v.viewed_at) AS last_view
                              FROM shares s LEFT JOIN share_views v ON v.token = s.token
                              WHERE s.matter_id = ? GROUP BY s.token ORDER BY s.created_at DESC""",
                           (str(matter_id),)).fetchall()
    return [dict(r) for r in rows]


def record_view(token: str, user_agent: str = "") -> None:
    with _db() as con:
        con.execute("INSERT INTO share_views VALUES (?, ?, ?)", (token, now(), user_agent))


# ---------- corrections to money cards ----------
def save_card_edit(matter_id, card_key: str, value: float, note: str = "", edited_by: str = "",
                   clio_value: float | None = None) -> None:
    """Save (or replace) a correction. clio_value = what Clio said at the time, so we notice if Clio changes later.
    Every save goes to the audit log too, so earlier values are never lost."""
    with _db() as con:
        con.execute("INSERT OR REPLACE INTO card_edits VALUES (?,?,?,?,?,?,?)",
                    (str(matter_id), card_key, float(value), note, edited_by, now(), clio_value))
        log("card_edited", f"{matter_id}:{card_key}",
            {"value": value, "clio_value": clio_value, "note": note}, con, actor=edited_by)


def clear_card_edit(matter_id, card_key: str, edited_by: str = "") -> None:
    """Go back to the Clio number."""
    with _db() as con:
        con.execute("DELETE FROM card_edits WHERE matter_id = ? AND card_key = ?", (str(matter_id), card_key))
        log("card_edit_removed", f"{matter_id}:{card_key}", {}, con, actor=edited_by)


def card_edits(matter_id) -> dict:
    """{card key: {value, note, edited_by, edited_at, clio_value}} for one case."""
    with _db() as con:
        rows = con.execute("SELECT * FROM card_edits WHERE matter_id = ?", (str(matter_id),)).fetchall()
    return {r["card_key"]: dict(r) for r in rows}


def card_reviews(matter_id) -> dict:
    """{card key: {status, value, by, at}} for one case."""
    with _db() as con:
        rows = con.execute("SELECT * FROM card_reviews WHERE matter_id = ?", (str(matter_id),)).fetchall()
    return {r["card_key"]: dict(r) for r in rows}


def set_card_review(matter_id, card_key: str, status: str, value: float | None, by: str = "",
                    snapshot: str = "") -> None:
    """Save what a person decided about a card, for the number it shows and the case snapshot they looked at
    (snapshot = the snapshot's fetched_at). Called only on a click, never while drawing the page."""
    with _db() as con:
        old = con.execute("SELECT status FROM card_reviews WHERE matter_id = ? AND card_key = ?",
                          (str(matter_id), card_key)).fetchone()
        con.execute("INSERT OR REPLACE INTO card_reviews (matter_id, card_key, status, value, by, at, snapshot) "
                    "VALUES (?,?,?,?,?,?,?)", (str(matter_id), card_key, status, value, by, now(), snapshot))
        log("card_review", f"{matter_id}:{card_key}",
            {"status": status, "was": old["status"] if old else None, "value": value, "snapshot": snapshot},
            con, actor=by)


def purge_matter(matter_id, by: str = "") -> dict:
    """Retention: remove what we keep about one case (edits, reviews, last-opened), turn off its share links
    and blank their frozen copies. The audit log keeps the record that it happened (it is append-only)."""
    mid = str(matter_id)
    with _db() as con:
        n = {t: con.execute(f"DELETE FROM {t} WHERE matter_id = ?", (mid,)).rowcount
             for t in ("card_edits", "card_reviews", "last_opened")}
        n["shares"] = con.execute("UPDATE shares SET revoked = 1, edited_text = '{}' WHERE matter_id = ?",
                                  (mid,)).rowcount
        log("matter_purged", mid, n, con, actor=by)
    return n


# ---------- last opened ----------
def last_opened(user_id: str, matter_id: str) -> str | None:
    with _db() as con:
        r = con.execute("SELECT opened_at FROM last_opened WHERE user_id = ? AND matter_id = ?",
                        (str(user_id), str(matter_id))).fetchone()
    return r["opened_at"] if r else None


def mark_opened(user_id: str, matter_id: str) -> None:
    with _db() as con:
        con.execute("INSERT OR REPLACE INTO last_opened VALUES (?, ?, ?)", (str(user_id), str(matter_id), now()))


def emails_for(token: str) -> list[dict]:
    """Emails sent with this link, oldest first (from the audit log)."""
    with _db() as con:
        rows = con.execute("SELECT at, detail FROM audit WHERE action = 'email_sent' AND item_id = ? ORDER BY at",
                           (share_ref(token),)).fetchall()
    return [{"at": r["at"], **json.loads(r["detail"])} for r in rows]


def nice_time(iso: str | None) -> str:
    """'2026-10-02T18:05:00+00:00' -> 'Oct 2, 11:05 AM' in local time."""
    if not iso:
        return ""
    try:
        return datetime.fromisoformat(iso).astimezone().strftime("%b %-d, %-I:%M %p")
    except ValueError:
        return iso
