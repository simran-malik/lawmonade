import json

import pytest
from pydantic import BaseModel

from app import llm, usage
from app.config import settings


class Digest(BaseModel):
    items: list[str]


def test_mock_reads_fixture_without_any_key(tmp_path, monkeypatch):
    (tmp_path / "Digest.json").write_text(json.dumps({"items": ["SOL is Jun 3"]}))
    monkeypatch.setattr(settings, "llm_provider", "mock")
    monkeypatch.setattr(settings, "llm_fixtures_dir", tmp_path)
    monkeypatch.setattr(settings, "anthropic_api_key", "")
    assert llm.ask_json("anything", Digest).items == ["SOL is Jun 3"]
    assert llm.ask("hi") == llm.MOCK_TEXT


def test_mock_without_fixture_says_what_to_do(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "mock")
    monkeypatch.setattr(settings, "llm_fixtures_dir", tmp_path)
    with pytest.raises(RuntimeError, match="Digest.json"):
        llm.ask_json("x", Digest)


def test_usage_totals_and_cost(monkeypatch):
    usage.reset()
    monkeypatch.setattr(settings, "llm_price_in_per_mtok", 0.0)
    monkeypatch.setattr(settings, "llm_price_out_per_mtok", 0.0)
    usage.record("anthropic", "m", 1000, 200)
    assert usage.totals() == {"calls": 1, "input_tokens": 1000, "output_tokens": 200, "cost_usd": None}
    monkeypatch.setattr(settings, "llm_price_in_per_mtok", 2.0)
    monkeypatch.setattr(settings, "llm_price_out_per_mtok", 10.0)
    usage.record("anthropic", "m", 1_000_000, 100_000)
    assert abs(usage.totals()["cost_usd"] - (1_001_000 * 2 + 100_200 * 10) / 1e6) < 1e-9
    usage.reset()
