"""Lien breakdown: AI answer is checked by code. Uses a fake AI, no keys needed."""
import json
from pathlib import Path

from app.kpis import kpis
from app.liens import LienBreakdown, analyze

TEXT = ("New York State Medicaid lien, $22,180.00 asserted. Progressive no-fault: $50,000 basic economic loss "
        "exhausted, which under Insurance Law 5104(a) is not recoverable from the tortfeasor. Social Security "
        "Disability claim filed and pending. Defendants pleaded CPLR 4545 collateral source.")
SNAP = {"source": "clio", "matter": {"url": "https://app.clio.com/nc/#/matters/7"},
        "fields": {"Health Insurance or Lien Holder": TEXT},
        "notes": [{"title": "Medicaid lien", "text": "Asserted figure unchanged at $22,180.00.",
                   "src": {"label": "Note · Jul 23, 2025 · Medicaid lien", "url": "u1"}}],
        "communications": [], "tasks": [], "calendar": [], "documents": [], "expenses": []}
FIXTURE = json.loads((Path(__file__).parent.parent / "data/fixtures/llm/LienBreakdown.json").read_text())


def fake(answer):
    return lambda prompt, schema: schema.model_validate(answer)


def test_only_real_liens_are_added_up():
    a = analyze(SNAP, fake(FIXTURE))
    assert a["status"] == "ok" and a["total"] == 22180 and not a["unchecked"]
    card = {k["key"]: k for k in kpis(SNAP, a)}["lien"]
    assert card["value"] == "$22,180" and card["sure"][0] == "ai" and "Not counted" in card["sub"]
    assert "Progressive" in card["sub"] and "1 other Clio item" in card["sub"]
    assert any("Note · Jul 23, 2025" in i["text"] for i in card["items"])


def test_made_up_quote_is_left_out():
    bad = {"items": [dict(FIXTURE["items"][0], quote="Medicare lien, $22,180.00 asserted.")]}
    a = analyze(SNAP, fake(bad))
    assert a["total"] is None and len(a["unchecked"]) == 1
    card = {k["key"]: k for k in kpis(SNAP, a)}["lien"]
    assert card["sure"][0] == "check" and card["warn"]


def test_wrong_amount_is_left_out():
    bad = {"items": [dict(FIXTURE["items"][0], amount=21180.0)]}
    assert analyze(SNAP, fake(bad))["unchecked"][0]["why"] == "The AI's amount is not in its quote."


def test_ai_unavailable_falls_back_to_plain_reading():
    def boom(prompt, schema):
        raise RuntimeError("ANTHROPIC_API_KEY is empty in .env")
    a = analyze(SNAP, boom)
    card = {k["key"]: k for k in kpis(SNAP, a)}["lien"]
    assert a["status"] == "failed" and card["value"] == "$22,180" and "unavailable" in card["why"]


def test_fixture_matches_schema():
    LienBreakdown.model_validate(FIXTURE)
