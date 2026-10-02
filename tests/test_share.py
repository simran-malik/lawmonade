"""Provider sharing: only chosen sections and ticked items reach the provider. No keys needed."""
from app import share

SNAP = {
    "source": "sample", "fetched_at": "2026-10-02T17:00:00+00:00",
    "matter": {"status": "Open", "stage": "Litigation", "client": "Pat Doe"},
    "fields": {"Policy Limits": "Defendant: $100,000"},
    "contacts": [{"id": "1", "name": "Acme Physical Therapy", "role": "Treating provider, physical therapy"},
                 {"id": "2", "name": "Big Insurance Co", "role": "No-fault carrier"},
                 {"id": "3", "name": "Jane Smith", "role": "Medical provider: neurology"}],
    "tasks": [{"id": "t1", "title": "By medical provider: Acme Physical Therapy - Treatment notes", "text": "",
               "status": "pending", "date": "2026-10-14"},
              {"id": "t2", "title": "Call Acme re records", "text": "", "status": "complete", "date": "2026-01-01"}],
    "expenses": [{"id": "x1", "title": "Medical treatment charges; Acme Physical Therapy", "text": "", "category": "",
                  "amount": 1000.0}],
    "documents": [{"id": "d1", "title": "04-medical-records__created__acme-physical-therapy-records.pdf", "date": "2023-06-29"},
                  {"id": "d2", "title": "02-pleadings__doc-01__summons-complaint.pdf", "date": "2024-03-08"}],
}


def test_providers_only_medical():
    assert [p["name"] for p in share.providers(SNAP)] == ["Acme Physical Therapy", "Jane Smith"]


def test_name_keys():
    assert share.name_keys("Acme Physical Therapy") == ["acme"]
    assert share.name_keys("Jane Smith") == ["smith"]


def test_build_and_payload_only_ticked():
    d = share.build(SNAP, SNAP["contacts"][0])
    assert d["status"]["active"] and [t["id"] for t in d["needs"]] == ["t1"] and d["billed"] == 1000.0
    assert [x["id"] for x in d["records"]] == ["d1"]
    p = share.payload(d, ["status", "bills"], ["t1"], ["d1"], 1000.0, (20, 40), "Hi", "Firm")
    assert "needs" not in p and "records" not in p and "coverage" not in p
    assert p["bills"]["low"] == 600.0 and p["bills"]["high"] == 800.0


def test_task_note_and_billed_amount_are_not_shared_by_default():
    snap = {**SNAP, "tasks": [dict(SNAP["tasks"][0], text="Internal: push PT to build specials")]}
    d = share.build(snap, snap["contacts"][0])
    p = share.payload(d, ["needs", "bills"], ["t1"], [], 1000.0, (20, 40), "Hi", "Firm")
    assert p["needs"][0]["detail"] == "" and "billed" not in p["bills"]
    p = share.payload(d, ["needs"], ["t1"], [], None, (20, 40), "Hi", "Firm", note_ids=["t1"])
    assert p["needs"][0]["detail"].startswith("Internal")


def test_overdue_uses_the_firm_time_zone(monkeypatch):
    from datetime import date

    from app.config import settings
    monkeypatch.setattr(settings, "timezone", "America/Los_Angeles")
    # 06:00 UTC on Oct 15 is still Oct 14 in Los Angeles: not overdue on Oct 14
    assert share.local_date("2026-10-15T06:00:00Z") == date(2026, 10, 14)
    assert not share.overdue("2026-10-15T06:00:00Z", today=date(2026, 10, 14))
    assert share.overdue("2026-10-15T06:00:00Z", today=date(2026, 10, 15))
    assert not share.overdue("not a date")
