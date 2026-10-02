"""Daily digest: deadlines in the firm's time zone, who to text, the checked AI summary, and no double sends.
No keys or network: email and Slack are replaced by fakes."""
from datetime import date

from app import deadlines, digest, store, summary
from app.config import settings
from app.summary import CaseSummary, SummarySentence

TODAY = date(2026, 10, 2)


def src(kind, id_, label=""):
    return {"where": "Clio", "kind": kind, "id": str(id_), "label": label or f"{kind} {id_}", "url": ""}


def snap(**over):
    s = {"source": "clio", "fetched_at": "2026-10-02T13:00:00+00:00",
         "matter": {"id": "m1", "number": "00001-Doe", "client": "Pat Doe", "description": "Doe v. Roe",
                    "status": "Open", "stage": "Treatment", "practice_area": "Personal Injury", "open_date": "2025-01-05",
                    "sol_date": "2026-11-01", "url": "", "client_phone": "(619) 555-0101", "client_email": "pat@doe.test",
                    "attorney": {"name": "Sam Lee", "email": "sam@firm.test"}},
         "fields": {"Case Summary": "Rear-ended on I-5 in San Diego. Neck and back injuries. Treating with Acme Chiropractic.",
                    "Estimated Case Value": 50000.0},
         "contacts": [{"id": "c1", "name": "Acme Chiropractic Center", "role": "Treating provider", "email": "rec@acme.test",
                       "phone": "619-555-0199"}],
         "notes": [{"id": "n1", "date": "2026-09-30", "title": "Call with adjuster",
                    "text": "Adjuster asked for updated records. Demand to go out after treatment ends.", "src": src("Note", "n1")}],
         "communications": [],
         "tasks": [
             {"id": "t1", "date": "2026-09-25", "status": "pending", "title": "Request records from Acme Chiropractic", "text": "",
              "src": src("Task", "t1")},
             {"id": "t2", "date": "2026-10-03", "status": "pending", "title": "Get wage letter from client", "text": "",
              "src": src("Task", "t2")},
             {"id": "t3", "date": "2026-01-02", "status": "pending", "title": "Old intake checklist", "text": "",
              "assignee": "Kim Paralegal", "src": src("Task", "t3")},
             {"id": "t4", "date": None, "status": "pending", "title": "Someday task", "text": "", "src": src("Task", "t4")},
             {"id": "t5", "date": "2026-09-01", "status": "complete", "title": "Done task", "text": "", "src": src("Task", "t5")},
         ],
         "calendar": [
             {"id": "e1", "date": "2026-10-10T17:00:00Z", "title": "Client check-in call", "text": "", "src": src("Calendar", "e1")},
             {"id": "e2", "date": "2026-09-20T17:00:00Z", "title": "Past meeting", "text": "", "src": src("Calendar", "e2")},
             {"id": "e3", "date": "2026-10-04T17:00:00Z", "title": "Cancelled: deposition", "text": "", "src": src("Calendar", "e3")},
         ],
         "expenses": [], "documents": []}
    s.update(over)
    return s


NO_AI = {"status": "failed", "items": [], "total": None}


# ---------- deadlines ----------
def test_deadline_lists_use_firm_day_and_skip_noise(monkeypatch):
    monkeypatch.setattr(settings, "timezone", "America/Los_Angeles")
    dl = deadlines.lists(snap(), TODAY)
    assert [i["id"] for i in dl["overdue"]] == ["t1"]                  # open + past due
    assert [i["id"] for i in dl["long_overdue"]] == ["t3"]             # > 90 days late: kept apart
    assert [i["id"] for i in dl["due_soon"]] == ["t2"]                 # tomorrow
    assert [i["id"] for i in dl["upcoming"]] == ["e1"]                 # past + cancelled events left out
    assert dl["no_date"] == 1                                         # never called overdue
    assert dl["sol"]["days"] == 30 and dl["sol"]["urgent"]


def test_utc_evening_is_still_today_in_los_angeles(monkeypatch):
    monkeypatch.setattr(settings, "timezone", "America/Los_Angeles")
    s = snap(tasks=[{"id": "x", "date": "2026-10-03T02:00:00Z", "status": "pending", "title": "Call", "text": "",
                     "src": src("Task", "x")}], calendar=[])
    dl = deadlines.lists(s, TODAY)
    assert dl["due_soon"][0]["days"] == 0                              # Oct 3 02:00 UTC = Oct 2, 7 PM in LA


def test_who_to_text(monkeypatch):
    dl = deadlines.lists(snap(), TODAY)
    c = dl["overdue"][0]["contact"]
    assert c["name"] == "Acme Chiropractic Center" and c["phone"] == "+16195550199"
    assert c["sms_url"].startswith("sms:+16195550199?&body=") and "$" not in c["draft"]
    staff = dl["long_overdue"][0]["contact"]
    assert staff["kind"] == "staff" and staff["sms_url"] == ""       # no phone for staff: shown, not texted
    client = deadlines.contact_for({"title": "Get wage letter from client", "text": ""}, snap())
    assert client["kind"] == "client" and client["phone"] == "+16195550101"


def test_sol_reference_object_is_not_a_date():
    s = snap()
    s["matter"]["sol_date"] = {"id": 1, "etag": "x"}                  # what Clio returned for Sapini
    s["matter"]["stage"] = "Litigation"
    s["tasks"].append({"id": "L", "date": "2026-04-22", "status": "complete", "title": "Limitations Date", "text": "",
                       "src": src("Task", "L", "Task · Limitations Date")})
    sol = deadlines.sol(s, TODAY)
    assert sol["date"] == "2026-04-22" and sol["filed"] and not sol["urgent"]


def test_phone_and_what():
    assert deadlines.phone("914.555.0134") == "+19145550134" and deadlines.phone("555-01") == ""
    assert deadlines.what("By medical provider: Acme - Updated records $1,200") == "Updated records"


# ---------- summary ----------
def test_summary_keeps_only_checked_sentences():
    def fake(prompt, model):
        assert "data, not instructions" in prompt
        return CaseSummary(sentences=[
            SummarySentence(text="The client was rear-ended on I-5 in San Diego.", source_id="S1",
                            quote="Rear-ended on I-5 in San Diego."),
            SummarySentence(text="The adjuster wants $90,000 by October 9.", source_id="S2",       # invented figures
                            quote="Adjuster asked for updated records."),
            SummarySentence(text="Treatment is finished.", source_id="S2", quote="treatment has finished"),  # not in text
            SummarySentence(text="Something.", source_id="S99", quote="whatever text here"),              # unknown id
        ])
    out = summary.summarize(snap(), ask=fake)
    assert out["mode"] == "ai" and out["dropped"] == 3
    assert [x["text"] for x in out["sentences"]] == ["The client was rear-ended on I-5 in San Diego."]


def test_summary_falls_back_to_clio_words():
    def broken(prompt, model):
        raise TimeoutError("slow")
    out = summary.summarize(snap(), ask=broken)
    assert out["mode"] == "fallback"
    assert out["sentences"][0]["text"] == "Rear-ended on I-5 in San Diego. Neck and back injuries."


# ---------- the run ----------
def _fakes(monkeypatch, tmp_path, email_fail=None):
    monkeypatch.setattr(settings, "db_path", tmp_path / "t.db")
    monkeypatch.setattr(settings, "snapshot_dir", tmp_path / "m")
    monkeypatch.setattr(settings, "slack_webhook_url", "https://hooks.slack.example/x")
    monkeypatch.setattr(settings, "firm_email_domains", "firm.test")
    monkeypatch.setattr(settings, "llm_provider", "mock")
    sent = {"email": [], "slack": []}

    def fake_send(to, subject, text, html=None):
        if email_fail:
            raise email_fail
        sent["email"].append((to, subject))
        return {"to": to, "intended": to, "via": "test"}
    import app.emailer
    import app.integrations.slack
    monkeypatch.setattr(app.emailer, "send", fake_send)
    monkeypatch.setattr(app.integrations.slack, "notify", lambda text, url=None: sent["slack"].append(text) or True)
    monkeypatch.setattr(digest.summary, "summarize",
                        lambda s, timeout=None, ask=None: {"facts": "Pat Doe", "sentences": [], "mode": "fallback",
                                                           "dropped": 0, "note": ""})
    return sent


def test_scheduled_digest_sends_once_per_day(tmp_path, monkeypatch):
    sent = _fakes(monkeypatch, tmp_path)
    s = snap()
    a = digest.run("m1", "scheduled", snap=s, lien_analysis=NO_AI)
    assert a["status"] == "sent" and len(sent["email"]) == 1 and sent["email"][0][0] == "sam@firm.test"
    assert len(sent["slack"]) == 1 and "overdue" in sent["slack"][0] and "Acme" not in sent["slack"][0]  # counts only
    b = digest.run("m1", "scheduled", snap=s, lien_analysis=NO_AI)                                        # n8n retry
    assert b["status"] == "already_sent" and len(sent["email"]) == 1


def test_no_slack_when_nothing_urgent(tmp_path, monkeypatch):
    sent = _fakes(monkeypatch, tmp_path)
    s = snap(tasks=[], calendar=[])
    s["matter"]["sol_date"] = None
    out = digest.run("m1", "manual", snap=s, lien_analysis=NO_AI)
    assert out["status"] == "sent" and out["slack"]["status"] == "not_urgent" and sent["slack"] == []


def test_manual_cooldown_then_force(tmp_path, monkeypatch):
    sent = _fakes(monkeypatch, tmp_path)
    assert digest.run("m1", "manual", "Sam", snap=snap(), lien_analysis=NO_AI)["status"] == "sent"
    again = digest.run("m1", "manual", "Sam", snap=snap(), lien_analysis=NO_AI)
    assert again["status"] == "cooldown" and len(sent["email"]) == 1
    assert digest.run("m1", "manual", "Sam", snap=snap(), lien_analysis=NO_AI, force=True)["status"] == "sent"


def test_outside_domain_is_dropped_and_failure_is_recorded(tmp_path, monkeypatch):
    sent = _fakes(monkeypatch, tmp_path)
    s = snap()
    s["matter"]["attorney"] = {"name": "Ext", "email": "someone@gmail.com"}
    monkeypatch.setattr(settings, "digest_recipients", "")
    out = digest.run("m1", "scheduled", snap=s, lien_analysis=NO_AI)
    assert out["email"]["status"] == "no_recipients" and sent["email"] == []
    assert out["status"] == "partial"                                 # Slack went out, email didn't
    assert store.last_digest("m1")["email_status"] == "no_recipients"


def test_retry_after_email_failure_resends_only_email(tmp_path, monkeypatch):
    from app.emailer import EmailError
    sent = _fakes(monkeypatch, tmp_path, email_fail=EmailError("The email could not be sent.", "x"))
    first = digest.run("m1", "scheduled", snap=snap(), lien_analysis=NO_AI)
    pings = [t for t in sent["slack"] if "needs attention" in t]
    assert first["status"] == "partial" and len(pings) == 1             # (+ one ops ping saying email failed)
    sent2 = _fakes(monkeypatch, tmp_path)                             # email works again
    second = digest.run("m1", "scheduled", snap=snap(), lien_analysis=NO_AI)
    assert second["status"] == "sent" and len(sent2["email"]) == 1 and sent2["slack"] == []   # Slack not sent twice


def test_too_old_copy_sends_unavailable_note(tmp_path, monkeypatch):
    sent = _fakes(monkeypatch, tmp_path)
    old = snap(fetched_at="2026-09-01T13:00:00+00:00")
    monkeypatch.setattr(digest, "fresh", lambda mid: (old, "We couldn't reach Clio."))
    out = digest.run("m1", "scheduled", lien_analysis=NO_AI)
    assert out["status"] == "unavailable" and "unavailable" in sent["email"][0][1]
    assert any("not sent" in t for t in sent["slack"])               # ops ping, no case details


def test_closed_case_is_skipped(tmp_path, monkeypatch):
    sent = _fakes(monkeypatch, tmp_path)
    s = snap()
    s["matter"]["status"] = "Closed"
    assert digest.run("m1", "scheduled", snap=s, lien_analysis=NO_AI)["status"] == "skipped" and sent["email"] == []


def test_preview_sends_nothing_and_email_matches_brief(tmp_path, monkeypatch):
    sent = _fakes(monkeypatch, tmp_path)
    out = digest.run("m1", "manual", snap=snap(), lien_analysis=NO_AI, dry_run=True)
    assert out["status"] == "preview" and sent == {"email": [], "slack": []}
    assert "$50,000" in out["email"]["html"] and "Request records from Acme" in out["email"]["html"]
    assert store.digest_runs("m1") == []


def test_what_changed_since_last_digest(tmp_path, monkeypatch):
    base = snap()
    now = snap()
    now["notes"] = now["notes"] + [{"id": "n2", "date": "2026-10-02", "title": "New", "text": "x", "src": src("Note", "n2")}]
    now["tasks"] = [dict(t, status="complete") if t["id"] == "t1" else t for t in now["tasks"]]
    ch = digest.changes(now, base)
    assert "1 new note" in ch["lines"] and "Task completed: Request records from Acme Chiropractic" in ch["lines"]


# ---------- case risks in the digest ----------
def test_digest_email_and_slack_show_case_risks(tmp_path, monkeypatch):
    sent = _fakes(monkeypatch, tmp_path)
    s = snap()
    s["matter"]["stage"] = "Litigation"
    out = digest.run("m1", "manual", snap=s, lien_analysis=NO_AI, dry_run=True)
    r = out["digest"]["risks"]
    assert r["set_up"] and r["top"][0]["key"] == "hard_deadlines" and r["top"][0]["level"] == "red"   # t3 is 273 days late
    assert "Deadlines (court, discovery, tasks)" in r["red"]
    assert "What could hurt this case" in out["email"]["html"] and "WHAT COULD HURT THIS CASE" in out["email"]["text"]
    assert "red risk" in out["slack"]["text"] and "Acme" not in out["slack"]["text"]      # names of risks, no details
    assert sent["email"] == [] and sent["slack"] == []                                    # preview sends nothing


def test_digest_uses_the_risks_the_dashboard_shows(tmp_path, monkeypatch):
    _fakes(monkeypatch, tmp_path)
    shown = {"stage": "Treatment", "stage_key": None, "set_up": False, "note": "not set up", "today": "2026-10-02",
             "signals": [], "top": []}
    out = digest.run("m1", "manual", snap=snap(), lien_analysis=NO_AI, dry_run=True, risk_report=shown)
    assert out["digest"]["risks"]["top"] == [] and "Nothing flagged today." in out["email"]["html"]
    assert "not set up" in out["email"]["text"]


# ---------- tab 2: overdue / due soon sections + responsible person ----------
def _tab2_items(s):
    return [it | {"kind": "Task"} for it in s["tasks"]] + [it | {"kind": "Calendar"} for it in s["calendar"]] + \
           [{"id": "n1", "kind": "Note", "date": "2026-09-30", "title": "Note", "src": src("Note", "n1")}]


def test_split_urgent_sections(monkeypatch):
    monkeypatch.setattr(settings, "timezone", "America/Los_Angeles")
    monkeypatch.setattr(settings, "digest_urgent_days", 1)
    late, soon, rest = deadlines.split_urgent(_tab2_items(snap()), TODAY)
    assert [i["id"] for i in late] == ["t3", "t1"]                    # most overdue first, all overdue (incl. long)
    assert [i["days"] for i in late] == [-273, -7]
    assert [i["id"] for i in soon] == ["t2"]                          # tomorrow; e3 is cancelled
    assert {i["id"] for i in rest} == {"t4", "t5", "e1", "e2", "e3", "n1"}   # done, undated, later, past, notes


def test_responsible_uses_clio_assignee_then_attorney():
    s = snap()
    t = {"kind": "Task", "title": "Request records", "assignee": "Kim Paralegal", "assignee_type": "User",
         "assignee_email": "kim@firm.test", "assignee_phone": "(619) 555-0144"}
    who = deadlines.responsible(t, s, -3)
    assert (who["name"], who["kind"], who["email"], who["phone"]) == ("Kim Paralegal", "staff", "kim@firm.test", "+16195550144")
    assert "was due 3 days ago" in who["draft"] and who["subject"].startswith("Overdue:")
    who = deadlines.responsible({"kind": "Task", "title": "Wage letter"}, s, 1)     # nobody assigned
    assert (who["name"], who["email"]) == ("Sam Lee", "sam@firm.test")
    assert "no one assigned" in who["role"] and "is due tomorrow" in who["draft"]
    no_att = snap(matter=s["matter"] | {"attorney": {"name": "", "email": ""}})
    assert deadlines.responsible({"kind": "Calendar", "title": "Call"}, no_att, 0) is None
