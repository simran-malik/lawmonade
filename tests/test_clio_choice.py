"""Several Clio cases match a search: never open the first one silently."""
import pytest

from app import clio
from app.config import settings

ROWS = [{"id": 1, "display_number": "00001", "description": "Auto", "status": "Open", "client": {"name": "Ann Smith"}},
        {"id": 2, "display_number": "00002", "description": "Slip", "status": "Open", "client": {"name": "Bob Smith"}}]


def fake_clio(monkeypatch):
    monkeypatch.setattr(settings, "clio_access_token", "t")
    monkeypatch.setattr(clio, "_get_all", lambda path, params, fields: ROWS if path == "matters.json" else [])

    class R:
        def json(self):
            return {"data": {"custom_field_values": []}}
    monkeypatch.setattr(clio, "_get", lambda url, params=None: R())


def test_two_matches_ask_a_person_to_pick(monkeypatch):
    fake_clio(monkeypatch)
    st, steps = clio.load_steps("Smith")
    with pytest.raises(clio.ClioChoice) as e:
        steps[0][1]()
    assert [c["client"] for c in e.value.choices] == ["Ann Smith", "Bob Smith"]


def test_picked_case_opens(monkeypatch):
    fake_clio(monkeypatch)
    st, steps = clio.load_steps("Smith", matter_id=2)
    steps[0][1]()
    assert st["matter"]["client"] == "Bob Smith"
