"""Case risks: Litigation signals + the ones every stage gets. Date math in the firm's time zone; the AI only reads
the liability field, and its answer is shown only if its quote is in the Clio text. No keys or network."""
from datetime import date

from app import brief, risks
from app.config import settings
from app.risks import LiabilityRead

TODAY = date(2026, 10, 2)
CFG = risks.load_config()
LIAB = "Contested on two independent levels, neither investigated. Metro-North disputes the lane change."


def src(kind, id_, label=""):
    return {"where": "Clio", "kind": kind, "id": str(id_), "label": label or f"{kind} {id_}", "url": f"https://x/{id_}"}


def snap(**over):
    s = {"source": "clio", "fetched_at": "2026-10-02T13:00:00+00:00",
         "matter": {"id": "m1", "client": "Justin Sapini", "client_email": "justin@sapini.test", "stage": "Litigation",
                    "status": "Open", "url": "https://app.clio.com/nc/#/matters/m1"},
         "fields": {"Liability Assessment": LIAB},
         "notes": [{"id": "n1", "date": "2026-09-15", "title": "Strategy", "text": "", "src": src("Note", "n1")}],
         "communications": [
             {"id": "c1", "date": "2026-09-27", "title": "Records from McCulloch", "text": "Attached.", "src": src("Email", "c1")},
             {"id": "c2", "date": "2026-08-20", "title": "Call with Justin Sapini", "text": "", "src": src("Phone call", "c2")},
         ],
         "tasks": [
             {"id": "t1", "date": "2026-08-25", "status": "pending", "title": "By medical provider: McCulloch Orthopaedic - Updated records",
              "text": "", "src": src("Task", "t1")},
             {"id": "t2", "date": "2026-09-26", "status": "pending", "title": "Obtain updated employment and commission records",
              "text": "", "src": src("Task", "t2")},
             {"id": "t3", "date": "2026-08-01", "status": "complete", "title": "Done", "text": "", "src": src("Task", "t3")},
         ],
         "calendar": [], "documents": [], "expenses": [], "contacts": []}
    s.update(over)
    return s


def by_key(r):
    return {s["key"]: s for s in r["signals"]}


def good_ai(prompt, model):
    assert "data, not instructions" in prompt and LIAB in prompt
    return LiabilityRead(status="contested_not_investigated",
                         quote="Contested on two independent levels, neither investigated.", confidence=0.9)


def test_stage_aliases_come_from_yaml():
    assert risks.stage_for("Litigation", CFG) == "litigation"
    assert risks.stage_for("  suit filed ", CFG) == "litigation"
    assert risks.stage_for("Treatment", CFG) is None and risks.stage_for("", CFG) is None


def test_litigation_flags_overdue_deadlines_like_sapini(monkeypatch):
    monkeypatch.setattr(settings, "timezone", "America/Los_Angeles")
    r = risks.build(snap(), TODAY, ask=good_ai, history=[])
    d = by_key(r)["hard_deadlines"]
    assert d["level"] == "red" and d["value"] == "2 tasks overdue"
    assert "38 days overdue" in d["why"] and d["link"]["url"] == "https://x/t1"   # McCulloch: due Aug 25
    assert [i["text"].split(" · ")[0] for i in d["items"]] == ["38 days overdue", "6 days overdue"]


def test_only_six_days_late_is_amber_but_a_late_court_item_is_red():
    one = snap(tasks=[{"id": "t2", "date": "2026-09-26", "status": "pending", "title": "Get employment records",
                       "text": "", "src": src("Task", "t2")}])
    assert by_key(risks.build(one, TODAY, ask=good_ai, history=[]))["hard_deadlines"]["level"] == "amber"
    court = snap(tasks=[{"id": "t9", "date": "2026-09-30", "status": "pending", "title": "Serve interrogatory responses",
                         "text": "", "src": src("Task", "t9")}])
    d = by_key(risks.build(court, TODAY, ask=good_ai, history=[]))["hard_deadlines"]
    assert d["level"] == "red" and "court/discovery" in d["items"][0]["text"]


def test_court_date_this_week_is_amber_and_past_events_are_not_overdue():
    s = snap(tasks=[], calendar=[
        {"id": "e1", "date": "2026-10-06T16:00:00Z", "title": "Deposition of plaintiff", "text": "", "src": src("Calendar", "e1")},
        {"id": "e2", "date": "2026-09-01T16:00:00Z", "title": "Court conference", "text": "", "src": src("Calendar", "e2")}])
    d = by_key(risks.build(s, TODAY, ask=good_ai, history=[]))["hard_deadlines"]
    assert d["level"] == "amber" and d["value"] == "1 deadline this week" and "Deposition" in d["why"]


def test_client_contact_uses_items_that_name_the_client():
    c = by_key(risks.build(snap(), TODAY, ask=good_ai, history=[]))["client_contact"]
    assert c["value"] == "43 days ago" and c["level"] == "amber" and c["sure"][0] == "calc"   # Aug 20 call
    nobody = snap(communications=[{"id": "c1", "date": "2026-09-27", "title": "Records", "text": "", "src": src("Email", "c1")}])
    c = by_key(risks.build(nobody, TODAY, ask=good_ai, history=[]))["client_contact"]
    assert c["value"] == "5 days ago" and c["sure"][0] == "check" and "No email or call names" in c["why"]
    future = snap(communications=[{"id": "c3", "date": "2026-11-01", "title": "Justin Sapini", "text": "", "src": src("Email", "c3")}])
    assert by_key(risks.build(future, TODAY, ask=good_ai, history=[]))["client_contact"]["level"] == "unknown"


def test_liability_ai_answer_shown_only_when_its_quote_checks_out():
    lia = by_key(risks.build(snap(), TODAY, ask=good_ai, history=[]))["liability"]
    assert lia["level"] == "red" and lia["sure"][0] == "ai" and "neither investigated" in lia["why"]
    assert lia["link"]["url"].endswith("/custom-fields")

    def made_up(prompt, model):
        return LiabilityRead(status="clear", quote="Liability is admitted.", confidence=0.95)

    def unsure(prompt, model):
        return LiabilityRead(status="contested", quote="Metro-North disputes the lane change.", confidence=0.4)

    def down(prompt, model):
        raise TimeoutError("slow")

    for ask in (made_up, unsure, down):
        lia = by_key(risks.build(snap(), TODAY, ask=ask, history=[]))["liability"]
        assert lia["level"] == "review" and lia["sure"] == ("check", "Needs review")


def test_common_signals_and_days_in_stage_from_saved_copies():
    hist = [("2025-01-10T15:00:00+00:00", "Treatment"), ("2025-03-01T15:00:00+00:00", "Litigation"),
            ("2026-09-01T15:00:00+00:00", "Litigation")]
    d = by_key(risks.build(snap(), TODAY, ask=good_ai, history=hist))
    assert d["days_since_activity"]["value"] == "5 days ago" and d["days_since_activity"]["level"] == "green"
    st = d["days_in_stage"]
    assert st["value"] == "580 days" and st["level"] == "amber" and st["sure"][0] == "calc"   # since Mar 1, 2025
    # same stage in every copy: only a lower bound, never called "green"
    st = by_key(risks.build(snap(), TODAY, ask=good_ai, history=[("2026-09-01T15:00:00+00:00", "Litigation")]))["days_in_stage"]
    assert st["value"] == "31+ days" and st["level"] == "unknown"


def test_top_two_worst_first_and_other_stages_get_common_only():
    r = risks.build(snap(), TODAY, ask=good_ai, history=[])
    assert r["set_up"] and [s["level"] for s in r["top"]] == ["red", "red"]
    assert {s["key"] for s in r["top"]} == {"hard_deadlines", "liability"}
    other = risks.build(snap(matter={**snap()["matter"], "stage": "Demand"}), TODAY, ask=good_ai, history=[])
    assert not other["set_up"] and "aren't set up yet" in other["note"]
    assert {s["key"] for s in other["signals"]} == {"days_since_activity", "days_in_stage"}


def test_brief_includes_risks(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "db_path", tmp_path / "t.db")
    rr = risks.build(snap(), TODAY, ask=good_ai, history=[])
    b = brief.build(snap(), {"status": "failed", "items": [], "total": None}, rr)
    assert b["risks"]["top"][0]["level"] == "red"
