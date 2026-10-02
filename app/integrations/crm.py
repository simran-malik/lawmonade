"""A fake CRM. Reads leads from a Google Sheet (published as CSV) or from data/crm_leads.csv.

load_leads()            -> list of dicts, one per lead
In production this would be Lawmatics, Filevine or Clio. Say so in the pitch.
"""
import csv
import io
import urllib.request

from app.config import ROOT, settings

LOCAL_CSV = ROOT / "data" / "crm_leads.csv"


def load_leads() -> list[dict]:
    if settings.crm_csv_url:
        with urllib.request.urlopen(settings.crm_csv_url, timeout=15) as r:
            text = r.read().decode("utf-8")
    else:
        text = LOCAL_CSV.read_text()
    return list(csv.DictReader(io.StringIO(text)))
