"""The case brief is built once for the dashboard and the API, and building it never writes to the DB."""
from app import brief, snapshot, store
from app.config import settings
from app.kpis import field_report, load_field_names

SNAP = {"source": "clio", "fetched_at": "2026-10-02T17:00:00+00:00",
        "matter": {"id": "m1", "url": "https://app.clio.com/nc/#/matters/m1", "client": "Pat Doe"},
        "fields": {"Estimated Case Value": 375000.0, "Policy Limits": "Defendant: $100,000",
                   "Medical Specials To Date": 118400.0, "Firm Notes": "x"},
        "notes": [], "communications": [], "tasks": [], "calendar": [], "documents": [], "expenses": [], "contacts": []}
NO_AI = {"status": "failed", "items": [], "total": None}


def test_brief_has_cards_and_does_not_write(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "db_path", tmp_path / "t.db")
    b = brief.build(SNAP, NO_AI)
    cards = {c["key"]: c for c in b["cards"]}
    assert cards["case_value"]["amount"] == 375000.0 and cards["case_value"]["review"]["status"] == "not_required"
    assert b["liens_status"] == "failed" and b["counts"]["notes"] == 0
    assert store.card_reviews("m1") == {}                  # drawing a brief saved nothing


def test_approval_is_kept_for_the_same_number(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "db_path", tmp_path / "t.db")
    store.set_card_review("m1", "coverage", "approved", 100000.0, "Sam", snapshot=SNAP["fetched_at"])
    cards = {c["key"]: c for c in brief.build(SNAP, NO_AI)["cards"]}
    assert cards["coverage"]["review"]["status"] == "approved"


def test_snapshot_history_keeps_dated_copies(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "snapshot_dir", tmp_path)
    monkeypatch.setattr(settings, "snapshot_keep", 2)
    for hour in ("15", "16", "17"):
        snapshot.save({**SNAP, "fetched_at": f"2026-10-02T{hour}:00:00+00:00"})
    assert [p.stem for p in snapshot.versions("m1")] == ["20261002T160000", "20261002T170000"]
    assert snapshot.load_version("m1", "2026-10-02T16:00:00+00:00")["fetched_at"].startswith("2026-10-02T16")
    assert snapshot.load_saved("m1")["fetched_at"].startswith("2026-10-02T17")
    assert snapshot.purge("m1") == 3 and snapshot.load_saved("m1") is None


def test_field_mapping_comes_from_yaml_and_reports_gaps(tmp_path):
    f = tmp_path / "fields.yaml"
    f.write_text("case_value: [Projected Settlement]\n")
    names = load_field_names(f)
    assert names["case_value"] == ["Projected Settlement"] and "Policy Limits" in names["coverage"]
    rep = field_report(SNAP)
    assert rep["cards"]["case_value"] == "Estimated Case Value" and rep["cards"]["liens"] is None
    assert rep["unmapped_fields"] == ["Firm Notes"]
