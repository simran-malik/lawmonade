import pytest
from pydantic import BaseModel

from app import llm_cache
from app.config import settings


class Answer(BaseModel):
    text: str


def counter(value="hi"):
    def call():
        call.n += 1
        return Answer(text=value)
    call.n = 0
    return call


def use(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "llm_cache_dir", tmp_path)
    return tmp_path


def test_second_call_is_a_cache_hit(tmp_path, monkeypatch):
    cache_dir = use(tmp_path, monkeypatch)
    call = counter()
    a = llm_cache.cached("prompt", Answer, call, "anthropic", "m1", mode="on")
    b = llm_cache.cached("prompt", Answer, call, "anthropic", "m1", mode="on")
    assert a == b and call.n == 1 and len(list(cache_dir.glob("*.json"))) == 1


def test_key_changes_with_model_prompt_and_schema():
    class Other(BaseModel):
        text: str
        extra: int = 0
    base = llm_cache.key("anthropic", "m1", Answer, "p")
    assert base != llm_cache.key("anthropic", "m2", Answer, "p")
    assert base != llm_cache.key("anthropic", "m1", Answer, "p2")
    assert base != llm_cache.key("anthropic", "m1", Other, "p")
    assert base == llm_cache.key("anthropic", "m1", Answer, "p")


def test_off_always_calls_and_saves_nothing(tmp_path, monkeypatch):
    cache_dir = use(tmp_path, monkeypatch)
    call = counter()
    llm_cache.cached("p", Answer, call, "anthropic", "m1", mode="off")
    llm_cache.cached("p", Answer, call, "anthropic", "m1", mode="off")
    assert call.n == 2 and not list(cache_dir.glob("*.json"))


def test_only_never_calls(tmp_path, monkeypatch):
    cache_dir = use(tmp_path, monkeypatch)
    call = counter()
    with pytest.raises(llm_cache.CacheMiss, match="--cache on"):
        llm_cache.cached("p", Answer, call, "anthropic", "m1", mode="only")
    llm_cache.cached("p", Answer, call, "anthropic", "m1", mode="on")
    assert llm_cache.cached("p", Answer, call, "anthropic", "m1", mode="only").text == "hi" and call.n == 1


def test_broken_entry_is_ignored(tmp_path, monkeypatch):
    cache_dir = use(tmp_path, monkeypatch)
    k = llm_cache.key("anthropic", "m1", Answer, "p")
    (cache_dir / f"{k}.json").write_text("{not json")
    call = counter("fresh")
    assert llm_cache.cached("p", Answer, call, "anthropic", "m1", mode="on").text == "fresh"


def test_bad_mode_is_a_clear_error(tmp_path, monkeypatch):
    cache_dir = use(tmp_path, monkeypatch)
    with pytest.raises(ValueError, match="LLM_CACHE"):
        llm_cache.cached("p", Answer, counter(), "anthropic", "m1", mode="sometimes")
