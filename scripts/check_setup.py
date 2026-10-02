"""Checks your setup. Run: bash run.sh check   (add --slack or --sms +1NUMBER to send a test)"""
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.config import ROOT, settings  # noqa: E402

ok = True


def check(name, passed, fix=""):
    global ok
    ok &= passed
    print(f"{'OK  ' if passed else 'FAIL'}  {name}" + ("" if passed else f"\n      fix: {fix}"))


check(".env", (ROOT / ".env").exists(), "cp .env.example .env")
check("tesseract installed", shutil.which("tesseract") is not None, "brew install tesseract")
check("Slack webhook (optional)", bool(settings.slack_webhook_url), "SETUP.md step 4")
check("Twilio keys (optional)", bool(settings.twilio_account_sid and settings.twilio_from_number), "SETUP.md step 6")
print(f"      LLM_PROVIDER = {settings.llm_provider}")
if settings.anthropic_api_key:
    try:
        import anthropic
        anthropic.Anthropic(api_key=settings.anthropic_api_key).messages.create(
            model=settings.anthropic_model, max_tokens=5, messages=[{"role": "user", "content": "Say OK"}])
        check(f"Claude API ({settings.anthropic_model})", True)
    except Exception as e:
        check("Claude API", False, str(e))
if settings.gemini_api_key:
    try:
        from app.gemini import gemini_text
        gemini_text("Say OK", max_tokens=10)
        check(f"Gemini API ({settings.gemini_model})", True)
    except Exception as e:
        check("Gemini API", False, str(e))
check("a key for the chosen LLM_PROVIDER",
      bool(settings.gemini_api_key if settings.llm_provider == "gemini" else settings.anthropic_api_key),
      "add ANTHROPIC_API_KEY or GEMINI_API_KEY to .env")

# Clio (read-only GET)
if settings.clio_access_token:
    try:
        import requests
        r = requests.get(f"{settings.clio_base}/api/v4/users/who_am_i.json", params={"fields": "name"},
                         headers={"Authorization": f"Bearer {settings.clio_access_token}"}, timeout=20)
        check(f"Clio API (signed in as {r.json()['data']['name']})" if r.ok else "Clio API", r.ok,
              f"HTTP {r.status_code}: redo REQUIREMENTS.md section 8, steps 5-6")
    except Exception as e:
        check("Clio API", False, str(e))
else:
    check("Clio access token in .env", False, "REQUIREMENTS.md section 8, steps 3-6")
check("Share link secret in .env", bool(settings.share_link_secret),
      'python3 -c "import secrets;print(secrets.token_urlsafe(32))" -> SHARE_LINK_SECRET')

# Field mapping (config/fields.yaml) against the cases saved so far
from app import snapshot  # noqa: E402
from app.kpis import field_report  # noqa: E402
for f in sorted(settings.snapshot_dir.glob("*/snapshot.json")):
    snap = snapshot.load_saved(f.parent.name)
    rep = field_report(snap)
    missing = [k for k, v in rep["cards"].items() if not v]
    check(f"Field mapping for case {snap['matter'].get('client') or f.parent.name}", not missing,
          f"no Clio field found for {', '.join(missing)}. Add the firm's field name to config/fields.yaml. "
          f"Fields on this case not used by any card: {', '.join(rep['unmapped_fields']) or 'none'}")

if "--slack" in sys.argv:
    try:
        from app.integrations.slack import notify
        check("Slack message sent", notify("Law-monade test message: Slack works."), "check SLACK_WEBHOOK_URL")
    except Exception as e:
        check("Slack message sent", False, str(e))

if "--sms" in sys.argv:
    to = sys.argv[sys.argv.index("--sms") + 1] if len(sys.argv) > sys.argv.index("--sms") + 1 else ""
    try:
        from app.integrations.sms import send_sms
        r = send_sms(to, "Law-monade test text: Twilio works.")
        check(f"Text sent to {to}", r.get("status") not in ("not_sent", "failed", None), r.get("reason") or str(r))
    except Exception as e:
        check("Text sent", False, f"{e}. Use: bash run.sh check --sms +1YOURNUMBER")

print("\nAll good." if ok else "\nFix the FAIL lines above.")
