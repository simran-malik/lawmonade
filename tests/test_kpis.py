"""Money numbers: done by code, with sources. No keys needed."""
from app.kpis import amounts, apply_edits, is_medical, kpis

SNAP = {
    "source": "sample",
    "fields": {"Estimated Case Value": 375000, "Policy Limits": "Defendant: $100,000 / $300,000\nUM: $25,000",
               "Health Insurance or Lien Holder": "Medicaid lien, $22,180.00 asserted", "Medical Specials To Date": "118400"},
    "expenses": [
        {"amount": 85.0, "title": "Records reproduction", "text": "Case expense, not patient treatment charges.",
         "category": "", "src": {"label": "Expense · Nov 9, 2023"}},
        {"amount": None, "title": "Medical treatment charges - clinic", "text": "", "category": "",
         "src": {"label": "Expense · Dec 1, 2023"}},
    ],
}


def test_amounts():
    assert amounts("Defendant: $100,000 / $300,000") == [100000.0, 300000.0]


def test_medical_split():
    assert not is_medical(SNAP["expenses"][0]) and is_medical(SNAP["expenses"][1])


def test_kpis_values_and_flags():
    k = {x["label"]: x for x in kpis(SNAP)}
    assert k["Case value (firm estimate)"]["value"] == "$375,000"
    cov = k["Coverage (first limit listed)"]
    assert cov["value"] == "$100,000" and cov["warn"] and "275,000" in cov["why"]
    assert k["Lien (first listed)"]["value"] == "$22,180"
    assert k["Medical bills to date"]["value"] == "$118,400"
    assert k["Firm has spent"]["value"] == "$85" and "1 provider bills" in k["Firm has spent"]["sub"]


def test_links_only_for_live_clio():
    assert all(k["link"] is None for k in kpis(SNAP))           # sample file: nothing to open
    live = {**SNAP, "matter": {"url": "https://app.clio.com/nc/#/matters/7"}}
    k = {x["key"]: x for x in kpis(live)}
    assert k["case_value"]["link"]["url"].endswith("/matters/7/custom-fields") and "Estimated Case Value" in k["case_value"]["link"]["hint"]
    assert k["firm_spend"]["link"]["url"].endswith("/matters/7/activities")


def test_edit_shows_new_number_and_keeps_clio_number():
    e = {"value": 50000.0, "note": "Adjuster confirmed", "edited_by": "Sam", "edited_at": "x", "clio_value": 100000.0}
    k = {x["key"]: x for x in apply_edits(kpis(SNAP), {"coverage": e})}
    c = k["coverage"]
    assert c["value"] == "$50,000" and c["sure"][0] == "edited" and "$100,000" in c["why"] and not c["warn"]
    assert "Adjuster confirmed" in c["why"]
    e2 = {**e, "clio_value": 90000.0}                            # Clio changed after the edit
    c2 = {x["key"]: x for x in apply_edits(kpis(SNAP), {"coverage": e2})}["coverage"]
    assert c2["warn"] and "changed since" in c2["why"]
