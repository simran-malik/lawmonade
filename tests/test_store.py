"""SQLite store: share links, views, last opened. Uses a temp database, no keys needed."""
from app import store
from app.config import settings


def test_share_link_flow(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "db_path", tmp_path / "t.db")
    token = store.create_share("m1", "c9", "Test Clinic", ["status", "bills"], days=1)
    s = store.get_share(token)
    assert s["provider_name"] == "Test Clinic" and s["allowed_fields"] == ["status", "bills"]
    store.record_view(token, "pytest")
    assert store.shares_for_matter("m1")[0]["views"] == 1
    store.revoke_share(token)
    assert store.get_share(token) is None


def test_expired_link_is_refused(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "db_path", tmp_path / "t.db")
    token = store.create_share("m1", "c9", "Test Clinic", ["status"], days=-1)
    assert store.get_share(token) is None


def test_last_opened(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "db_path", tmp_path / "t.db")
    assert store.last_opened("u1", "m1") is None
    store.mark_opened("u1", "m1")
    assert store.last_opened("u1", "m1") is not None


def test_email_log(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "db_path", tmp_path / "t.db")
    token = store.create_share("m1", "c9", "Test Clinic", ["status"], days=1)
    assert store.emails_for(token) == []
    store.log("email_sent", store.share_ref(token), {"to": "a@b.com", "intended": "a@b.com", "via": "gmail", "subject": "x"})
    assert store.emails_for(token)[0]["to"] == "a@b.com"


def test_card_edits(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "db_path", tmp_path / "t.db")
    store.save_card_edit("m1", "lien", 22000, "From lien letter", "Sam", 22180)
    e = store.card_edits("m1")["lien"]
    assert e["value"] == 22000 and e["clio_value"] == 22180 and e["edited_by"] == "Sam"
    store.clear_card_edit("m1", "lien")
    assert store.card_edits("m1") == {}


def test_card_reviews(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "db_path", tmp_path / "t.db")
    store.set_card_review("m1", "lien", "needs_review", 22180)
    store.set_card_review("m1", "lien", "approved", 22180, "Sam")
    r = store.card_reviews("m1")["lien"]
    assert r["status"] == "approved" and r["by"] == "Sam" and r["value"] == 22180


def test_audit_is_append_only_and_has_no_raw_tokens(tmp_path, monkeypatch):
    import sqlite3

    import pytest
    monkeypatch.setattr(settings, "db_path", tmp_path / "t.db")
    token = store.create_share("m1", "c9", "Test Clinic", ["status"], days=1, created_by="Sam")
    with store._db() as con:
        rows = con.execute("SELECT item_id, actor FROM audit").fetchall()
        assert rows[0]["item_id"] == store.share_ref(token) and rows[0]["actor"] == "Sam"
        assert token not in str([tuple(r) for r in rows])
        with pytest.raises(sqlite3.DatabaseError, match="append-only"):
            con.execute("DELETE FROM audit")
        with pytest.raises(sqlite3.DatabaseError, match="append-only"):
            con.execute("UPDATE audit SET actor = 'x'")


def test_old_database_is_upgraded_in_place(tmp_path, monkeypatch):
    import sqlite3
    db = tmp_path / "old.db"
    con = sqlite3.connect(db)            # the schema before migrations existed, with a raw token in audit
    con.executescript("""CREATE TABLE shares (token TEXT PRIMARY KEY, matter_id TEXT, provider_id TEXT,
        provider_name TEXT, allowed_fields TEXT, edited_text TEXT, created_by TEXT, created_at TEXT,
        expires_at TEXT, revoked INTEGER DEFAULT 0);
        CREATE TABLE card_reviews (matter_id TEXT, card_key TEXT, status TEXT, value REAL, by TEXT, at TEXT,
        PRIMARY KEY (matter_id, card_key));
        CREATE TABLE audit (at TEXT, action TEXT, item_id TEXT, detail TEXT);
        INSERT INTO shares (token, matter_id) VALUES ('tok123', 'm1');
        INSERT INTO audit VALUES ('2026-10-01', 'share_created', 'tok123', '{}');""")
    con.commit()
    con.close()
    monkeypatch.setattr(settings, "db_path", db)
    store._READY.discard(str(db))
    with store._db() as con:
        assert con.execute("PRAGMA user_version").fetchone()[0] == len(store.MIGRATIONS)
        assert con.execute("SELECT item_id FROM audit").fetchone()[0] == store.share_ref("tok123")
    store.set_card_review("m1", "lien", "approved", 1.0, "Sam", snapshot="2026-10-02T17:00:00+00:00")
    assert store.card_reviews("m1")["lien"]["snapshot"].startswith("2026-10-02")


def test_purge_matter(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "db_path", tmp_path / "t.db")
    token = store.create_share("m1", "c9", "Test Clinic", ["status"], edited_text='{"x": 1}', days=1)
    store.save_card_edit("m1", "lien", 1, "", "Sam", 2)
    n = store.purge_matter("m1", "Sam")
    assert n["card_edits"] == 1 and n["shares"] == 1
    assert store.get_share(token) is None and store.card_edits("m1") == {}
