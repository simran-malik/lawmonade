"""Send an email from the firm's pre-set address.

Two ways (pick in .env):
  1. Gmail API (default): uses credentials.json + a one-time sign-in -> token_gmail.json.  Run once: bash run.sh gmail
  2. SMTP: set SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD (for Gmail: an App Password).
EMAIL_DEMO_REDIRECT=you@example.com sends every email to you instead (the real recipient is shown in the subject).
Use it for the demo: Clio's sample contacts have fake .test addresses that can't receive mail.
"""
import base64
import smtplib
from email.message import EmailMessage

from app.config import ROOT, settings

GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.send"]
GMAIL_TOKEN = ROOT / "token_gmail.json"


class EmailError(Exception):
    def __init__(self, message: str, fix: str):
        super().__init__(message)
        self.message, self.fix = message, fix


def mode() -> str:
    if settings.smtp_host:
        return "smtp"
    return "gmail" if GMAIL_TOKEN.exists() else "none"


def sender() -> str:
    return settings.email_from or settings.smtp_user or "(the signed-in Gmail account)"


def _gmail_service(interactive: bool = False):
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    creds = Credentials.from_authorized_user_file(str(GMAIL_TOKEN), GMAIL_SCOPES) if GMAIL_TOKEN.exists() else None
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        elif interactive:
            from google_auth_oauthlib.flow import InstalledAppFlow
            flow = InstalledAppFlow.from_client_secrets_file(str(ROOT / "credentials.json"), GMAIL_SCOPES)
            creds = flow.run_local_server(port=0)
        else:
            raise EmailError("Email isn't set up yet.", "In Terminal run: bash run.sh gmail  (one-time Google sign-in).")
        GMAIL_TOKEN.write_text(creds.to_json())
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


def send(to: str, subject: str, text: str, html: str | None = None) -> dict:
    """Send one email. Returns {"to": who it actually went to, "intended": original recipient, "via": ...}."""
    to = (to or "").strip()
    if "@" not in to:
        raise EmailError("There's no valid email address to send to.", "Type the provider's email address, then try again.")
    real_to = settings.email_demo_redirect.strip() or to
    if real_to != to:
        subject = f"[Demo · meant for {to}] {subject}"

    msg = EmailMessage()
    msg["To"], msg["Subject"] = real_to, subject
    if settings.email_from:
        msg["From"] = settings.email_from
    msg.set_content(text)
    if html:
        msg.add_alternative(html, subtype="html")

    m = mode()
    try:
        if m == "smtp":
            with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30) as s:
                s.starttls()
                s.login(settings.smtp_user, settings.smtp_password)
                if "From" not in msg:
                    msg["From"] = settings.smtp_user
                s.send_message(msg)
        elif m == "gmail":
            raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
            _gmail_service().users().messages().send(userId="me", body={"raw": raw}).execute()
        else:
            raise EmailError("Email isn't set up yet.", "In Terminal run: bash run.sh gmail  (one-time Google sign-in).")
    except EmailError:
        raise
    except smtplib.SMTPAuthenticationError:
        raise EmailError("The email account rejected the password.", "Check SMTP_USER and SMTP_PASSWORD in .env.") from None
    except Exception as e:
        raise EmailError("The email could not be sent.", f"Check your internet and email setup, then try again. ({e})") from None
    return {"to": real_to, "intended": to, "via": m}


if __name__ == "__main__":      # bash run.sh gmail -> one-time sign-in
    _gmail_service(interactive=True)
    print(f"Gmail is ready. Token saved to {GMAIL_TOKEN.name} (not in git).")
