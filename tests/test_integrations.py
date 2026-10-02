from pathlib import Path

from app.config import settings
from app.integrations import crm, slack, sms

TEMPLATES = Path(__file__).resolve().parent.parent / "data" / "templates"


def test_crm_reads_local_csv(monkeypatch):
    monkeypatch.setattr(settings, "crm_csv_url", "")
    leads = crm.load_leads()
    assert len(leads) == 10 and leads[0]["name"] == "Maria Lopez"


def test_slack_and_sms_do_nothing_without_keys(monkeypatch):
    monkeypatch.setattr(settings, "slack_webhook_url", "")
    monkeypatch.setattr(settings, "twilio_account_sid", "")
    assert slack.notify("hi") is False
    assert sms.send_sms("+16195550101", "hi")["status"] == "not_sent"


def test_retainer_template_fills(tmp_path):
    from app.integrations.docs import fields_in, render_docx

    t = TEMPLATES / "retainer_agreement.docx"
    ctx = {f: "X" for f in fields_in(t)} | {"client_name": "Maria Lopez"}
    out = render_docx(t, ctx, tmp_path / "r.docx")
    from docx import Document
    text = "\n".join(p.text for p in Document(out).paragraphs)
    assert "Maria Lopez" in text and "{{" not in text


def test_trial_template_sends_template_name(monkeypatch):
    import io
    import json
    import urllib.parse

    sent = {}

    class Resp(io.BytesIO):
        def __enter__(self): return self
        def __exit__(self, *a): return False

    def fake_urlopen(req, timeout=0):
        sent.update(urllib.parse.parse_qs(req.data.decode()))
        return Resp(json.dumps({"sid": "SM1", "status": "queued"}).encode())

    monkeypatch.setattr(sms.urllib.request, "urlopen", fake_urlopen)
    for k, v in {"twilio_account_sid": "AC1", "twilio_auth_token": "t", "twilio_from_number": "+17370000000",
                 "twilio_trial_template": "sms_appointment_reminders"}.items():
        monkeypatch.setattr(settings, k, v)
    r = sms.send_sms("+18580000000", "Hi Maria, your deposition is Nov 4 at 10:00 AM.")
    assert sent["Body"] == ["sms_appointment_reminders"]
    assert r["intended_body"].startswith("Hi Maria") and r["sent_template"] == "sms_appointment_reminders"

    monkeypatch.setattr(settings, "twilio_trial_template", "my_own_text")
    assert sms.send_sms("+18580000000", "x")["status"] == "failed"
