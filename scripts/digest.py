"""Daily digest from the terminal (the same code as the n8n schedule and the dashboard button).
Use:  bash run.sh digest                         preview every watched case (nothing is sent)
      bash run.sh digest --matter 1811193158     preview one case -> logs/digest_preview.html (open it in a browser)
      bash run.sh digest --matter 1811193158 --send     send it now, as the schedule would (once per case per day)
Without --send nothing is sent and nothing is recorded.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app import digest, log  # noqa: E402
from app.config import ROOT  # noqa: E402


def arg(name: str, default: str = "") -> str:
    a = sys.argv
    return a[a.index(name) + 1] if name in a and a.index(name) + 1 < len(a) else default


log.setup()
send = "--send" in sys.argv
ids = [arg("--matter")] if arg("--matter") else [m["id"] for m in digest.watched()]
if not ids:
    sys.exit("No saved case yet. Open one in the dashboard first (bash run.sh ui).")
for mid in ids:
    r = digest.run(mid, "scheduled", actor="run.sh", dry_run=not send)
    print(f"Case {mid}: {r['status']} · {r.get('message', '')}")
    if not send and r["status"] == "preview":
        out = ROOT / "logs" / ("digest_preview.html" if len(ids) == 1 else f"digest_preview_{mid}.html")
        out.parent.mkdir(exist_ok=True)
        out.write_text(r["email"]["html"])
        print(f"  Subject: {r['email']['subject']}\n  To: {', '.join(r['email']['to']) or 'nobody (set DIGEST_RECIPIENTS)'}"
              f"\n  Slack: {r['slack']['text'] or 'no ping (nothing urgent)'}\n  Email preview: {out}")
