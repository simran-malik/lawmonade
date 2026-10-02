"""Our own SQLite store (outside Clio). Built into Python, one file: data/lawmonade.db.

Tables
  shares       provider share links: what the attorney chose to share, and when the link expires
  share_views  each time a share link is opened ("has anyone in their office opened it?")
  last_opened  when each user last opened each matter ("what changed since I last opened it?")
  audit        who did what, when (pattern taken from hack/app/store.py)

Clio snapshots and AI digests are JSON files in data/matters/, not here.
"""
import json
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone

from app.config import settings


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _db() -> sqlite3.Connection:
    settings.db_path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(settings.db_path, timeout=10)
    con.row_factory = sqlite3.Row
    con.executescript("""
        CREATE TABLE IF NOT EXISTS shares (
            token TEXT PRIMARY KEY, matter_id TEXT, provider_id TEXT, provider_name TEXT,
            allowed_fields TEXT, edited_text TEXT, created_by TEXT,
            created_at TEXT, expires_at TEXT, revoked INTEGER DEFAULT 0);
        CREATE TABLE IF NOT EXISTS share_views (token TEXT, viewed_at TEXT, user_agent TEXT);
        CREATE TABLE IF NOT EXISTS last_opened (
            user_id TEXT, matter_id TEXT, opened_at TEXT, PRIMARY KEY (user_id, matter_id));
        CREATE TABLE IF NOT EXISTS audit (at TEXT, action TEXT, item_id TEXT, detail TEXT);
    """)
    return con


def log(action: str, item_id: str, detail, con: sqlite3.Connection | None = None) -> None:
    row = (now(), action, item_id, json.dumps(detail))
    if con:
        con.execute("INSERT INTO audit VALUES (?, ?, ?, ?)", row)
    else:
        with _db() as c:
            c.execute("INSERT INTO audit VALUES (?, ?, ?, ?)", row)


# ---------- share links ----------
def create_share(matter_id: str, provider_id: str, provider_name: str, allowed_fields: list[str],
                 edited_text: str = "", created_by: str = "", days: int | None = None) -> str:
    token = secrets.token_urlsafe(24)
    expires = datetime.now(timezone.utc) + timedelta(days=days or settings.share_link_days)
    with _db() as con:
        con.execute("INSERT INTO shares VALUES (?,?,?,?,?,?,?,?,?,0)",
                    (token, str(matter_id), str(provider_id), provider_name, json.dumps(allowed_fields),
                     edited_text, created_by, now(), expires.isoformat(timespec="seconds")))
        log("share_created", token, {"matter": matter_id, "provider": provider_name, "fields": allowed_fields}, con)
    return token


def get_share(token: str) -> dict | None:
    """The share if it exists, is not revoked and has not expired. Else None."""
    with _db() as con:
        r = con.execute("SELECT * FROM shares WHERE token = ?", (token,)).fetchone()
    if not r or r["revoked"] or r["expires_at"] < now():
        return None
    d = dict(r)
    d["allowed_fields"] = json.loads(d["allowed_fields"])
    return d


def revoke_share(token: str) -> None:
    with _db() as con:
        con.execute("UPDATE shares SET revoked = 1 WHERE token = ?", (token,))
        log("share_revoked", token, "", con)


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
                           (token,)).fetchall()
    return [{"at": r["at"], **json.loads(r["detail"])} for r in rows]


def nice_time(iso: str | None) -> str:
    """'2026-10-02T18:05:00+00:00' -> 'Oct 2, 11:05 AM' in local time."""
    if not iso:
        return ""
    try:
        return datetime.fromisoformat(iso).astimezone().strftime("%b %-d, %-I:%M %p")
    except ValueError:
        return iso
