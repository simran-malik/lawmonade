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
    store.log("email_sent", token, {"to": "a@b.com", "intended": "a@b.com", "via": "gmail", "subject": "x"})
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
