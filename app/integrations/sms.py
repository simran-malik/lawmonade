"""Send a text message with Twilio. No extra packages needed.

send_sms("+16195550123", "Hi Maria, this is Example Law. Are you free for a call today?")

Twilio LIMITED TRIAL accounts can't send your own words, only one of Twilio's fixed templates,
and only to numbers you verified. Set TWILIO_TRIAL_TEMPLATE (e.g. sms_appointment_reminders):
the phone gets Twilio's fixed template text, and the message you meant to send is printed and
returned as "intended_body" so the screen can show it. Leave it empty on a paid account.
"""
import base64
import json
import urllib.error
import urllib.parse
import urllib.request

from app.config import settings
from app.log import get

LOG = get("sms")


TRIAL_TEMPLATES = {
    "sms_2fa", "sms_appointment_reminders", "sms_order_confirmation", "sms_delivery_updates",
    "sms_customer_support", "sms_marketing_promotions", "sms_event_notifications",
    "sms_account_alerts", "sms_feedback_surveys", "sms_internal_alerts",
}


def send_sms(to: str, body: str) -> dict:
    sid, token, sender = settings.twilio_account_sid, settings.twilio_auth_token, settings.twilio_from_number
    template = settings.twilio_trial_template.strip()
    if not (sid and token and sender):
        LOG.info("[send.sms] Twilio not set up; would text ...%s (%d characters)", to[-4:], len(body))
        return {"status": "not_sent", "reason": "Twilio keys missing in .env", "intended_body": body}
    if template and template not in TRIAL_TEMPLATES:
        return {"status": "failed", "reason": f"TWILIO_TRIAL_TEMPLATE '{template}' is not one of: "
                                              f"{', '.join(sorted(TRIAL_TEMPLATES))}"}
    if template:
        LOG.info("[send.sms] trial account: phone gets template %s instead of our %d-character message", template, len(body))
    url = f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json"
    data = urllib.parse.urlencode({"To": to, "From": sender, "Body": template or body}).encode()
    auth = base64.b64encode(f"{sid}:{token}".encode()).decode()
    req = urllib.request.Request(url, data=data, headers={"Authorization": f"Basic {auth}"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            out = json.loads(r.read())
        out["intended_body"] = body
        out["sent_template"] = template or None
        return out
    except urllib.error.HTTPError as e:   # show Twilio's own reason, not just "400"
        try:
            err = json.loads(e.read())
        except Exception:
            err = {}
        code, msg = err.get("code"), err.get("message", str(e))
        hint = HINTS.get(code, "")
        return {"status": "failed", "code": code, "intended_body": body,
                "reason": f"Twilio error {code}: {msg}{' -> ' + hint if hint else ''}",
                "more_info": err.get("more_info")}


HINTS = {
    21608: "Trial accounts can only text numbers you verified. Verify it in Twilio: Phone Numbers > Manage > Verified Caller IDs.",
    21211: "The 'To' number is not valid. Use +1 and 10 digits, no spaces.",
    21212: "TWILIO_FROM_NUMBER is not valid. Use your Twilio number like +1XXXXXXXXXX.",
    21606: "TWILIO_FROM_NUMBER can't send SMS. Use your Twilio number (not your own phone), and check it has SMS.",
    21659: "TWILIO_FROM_NUMBER is not a Twilio number on this account.",
    21266: "'To' and 'From' are the same number. Send to your own phone, from the Twilio number.",
    20003: "Wrong Account SID or Auth Token in .env.",
    572006: "Limited trial: set TWILIO_TRIAL_TEMPLATE=sms_appointment_reminders in .env (or upgrade Twilio).",
}
