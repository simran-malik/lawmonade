"""Google Calendar: event shape, "Add all" picks, and no duplicates. A fake Google service, no keys needed."""
from datetime import timedelta

import pytest

from app import gcal, store
from app.config import settings
from app.share import firm_now


class HttpError(Exception):          # same name as googleapiclient's, which is what gcal looks at
    def __init__(self, status):
        super().__init__(status)
        self.resp = type("R", (), {"status": status, "get": lambda self, k, d=None: d})()


class FakeCalendar:
    def __init__(self, fail_with=None):
        self.events_by_id, self.fail_with, self.calls = {}, fail_with, 0

    def events(self):
        return self

    def insert(self, calendarId, body):
        self.calls += 1
        fake = self

        class Req:
            def execute(self):
                if fake.fail_with:
                    raise HttpError(fake.fail_with)
                if body["id"] in fake.events_by_id:
                    raise HttpError(409)
                fake.events_by_id[body["id"]] = body
                return {"id": body["id"], "htmlLink": f"https://calendar.example/{body['id']}"}
        return Req()


def day(n: int) -> str:
    return (firm_now().date() + timedelta(days=n)).isoformat()


def snap():
    def it(kind, id_, date, title, **kw):
        return {"id": id_, "date": date, "title": title, "text": "details",
                "src": {"where": "Clio", "kind": kind, "id": id_, "label": f"{kind} · {title}",
                        "url": "https://app.clio.com/x", "hint": title}, **kw}
    return {"matter": {"id": "m1", "number": "00042", "client": "Maria Sapini", "url": "https://app.clio.com/m"},
            "tasks": [it("Task", "t1", day(3), "Request records", status="pending"),
                      it("Task", "t2", day(5), "Done already", status="complete"),
                      it("Task", "t3", day(-10), "Old task", status="pending"),
                      it("Task", "t4", None, "No date", status="pending")],
            "calendar": [it("Calendar", "e1", f"{day(7)}T17:00:00Z", "Deposition", end=f"{day(7)}T19:00:00Z"),
                         it("Calendar", "e2", f"{day(-30)}T17:00:00Z", "Past meeting")]}


@pytest.fixture(autouse=True)
def db(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "db_path", tmp_path / "t.db")
    monkeypatch.setattr(settings, "google_calendar_id", "primary")


def test_add_all_picks_upcoming_open_items_only():
    s = snap()
    assert [it["id"] for it in gcal.pending(s)] == ["t1", "e1"]


def test_event_shapes():
    s = snap()
    task = gcal.event_body(s, s["tasks"][0])
    assert task["start"] == {"date": day(3)} and "dateTime" not in task["end"]       # a due date is all-day
    assert task["summary"].startswith("Task due: Request records") and "Maria Sapini" in task["summary"]
    ev = gcal.event_body(s, s["calendar"][0])
    assert ev["start"]["dateTime"].startswith(day(7)) and ev["end"]["dateTime"].endswith("19:00:00+00:00")
    assert "https://app.clio.com/x" in ev["description"] and ev["source"]["url"] == "https://app.clio.com/x"
    ok = set("0123456789abcdefghijklmnopqrstuv")
    assert set(ev["id"]) <= ok and 5 <= len(ev["id"]) <= 1024


def test_add_is_saved_and_never_duplicated():
    s, svc = snap(), FakeCalendar()
    r = gcal.add(s, s["tasks"][0], "Sam", service=svc)
    assert r["status"] == "added" and "Task:t1" in gcal.added("m1")
    assert [it["id"] for it in gcal.pending(s)] == ["e1"]
    store._READY.clear()
    # pressed again (e.g. another person whose screen was stale): Google says 409, we report "already"
    assert gcal.add(s, s["tasks"][0], "Lee", service=svc)["status"] == "already"
    assert len(svc.events_by_id) == 1 and gcal.added("m1")["Task:t1"]["added_by"] == "Sam"


def test_add_many_and_errors(monkeypatch):
    s, svc = snap(), FakeCalendar()
    monkeypatch.setattr(gcal, "_service", lambda interactive=False: svc)
    r = gcal.add_many(s, gcal.pending(s), "Sam")
    assert r == {"added": 2, "already": 0, "failed": []} and gcal.pending(s) == []
    # past and finished items can still be added one by one
    assert gcal.add(s, s["calendar"][1], "Sam", service=svc)["status"] == "added"
    with pytest.raises(gcal.CalendarError):
        gcal.add(s, s["tasks"][3], service=svc)                    # no date
    bad = FakeCalendar(fail_with=404)
    monkeypatch.setattr(gcal, "_service", lambda interactive=False: bad)
    s2 = snap() | {"matter": {"id": "m2"}}
    r = gcal.add_many(s2, gcal.pending(s2))
    assert r["added"] == 0 and len(r["failed"]) == 1 and bad.calls == 1    # wrong calendar: stop after the first


def test_not_set_up(monkeypatch, tmp_path):
    monkeypatch.setattr(gcal, "TOKEN", tmp_path / "none.json")
    assert not gcal.ready()
    with pytest.raises(gcal.CalendarError):
        gcal._service()
