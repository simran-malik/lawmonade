"""Small LLM helpers. LLM_PROVIDER in .env (or --llm) picks the AI:
  anthropic = Claude,  gemini = Gemini,  mock = saved answers in data/fixtures/llm (no key, no Wi-Fi)

ask("Summarize this", text)            -> str
ask_json(prompt, MyPydanticModel)      -> MyPydanticModel   (Claude Structured Outputs / Gemini JSON mode)
                                          answers are cached on disk (see app/llm_cache.py, --cache on|off|only)
ask_image(png_bytes, "Transcribe...")  -> str
Every real call logs its time and token use (app/usage.py).
"""
import base64
import json
from typing import TypeVar

from pydantic import BaseModel

from app import llm_cache, usage
from app.config import settings
from app.log import get, stage

LOG = get("llm")
T = TypeVar("T", bound=BaseModel)
MOCK_TEXT = "[mock] No AI was called (LLM_PROVIDER=mock)."


def provider() -> str:
    """anthropic | gemini | mock (anything unknown means anthropic, as before)."""
    p = (settings.llm_provider or "anthropic").lower()
    return p if p in ("gemini", "mock") else "anthropic"


def model_name() -> str:
    return {"gemini": settings.gemini_model, "mock": "mock"}.get(provider(), settings.anthropic_model)


def _client():
    from app.claude import client  # 2-minute time limit, one retry
    return client()


def _record(msg) -> None:
    u = getattr(msg, "usage", None)
    usage.record("anthropic", settings.anthropic_model,
                 getattr(u, "input_tokens", 0), getattr(u, "output_tokens", 0))


# ---------- mock ----------
def mock_json(model: type[T]) -> T:
    """Saved answer for this schema: data/fixtures/llm/<SchemaName>.json."""
    f = settings.llm_fixtures_dir / f"{model.__name__}.json"
    if not f.exists():
        raise RuntimeError(f"Mock mode has no saved answer for {model.__name__}. "
                           f"Add {f.name} to data/fixtures/llm/, or use --llm anthropic.")
    return model.model_validate(json.loads(f.read_text()))


# ---------- public helpers ----------
def ask(prompt: str, text: str = "", system: str | None = None, max_tokens: int = 2000) -> str:
    """Plain-text answer (not cached)."""
    content = f"{prompt}\n\n{text}" if text else prompt
    if provider() == "mock":
        return MOCK_TEXT
    if provider() == "gemini":
        from app.gemini import gemini_text
        return gemini_text(f"{system}\n\n{content}" if system else content, max_tokens)
    kw = {"system": system} if system else {}
    with stage("llm.claude.text", LOG) as info:
        info.update(model=settings.anthropic_model)
        msg = _client().messages.create(model=settings.anthropic_model, max_tokens=max_tokens,
                                        messages=[{"role": "user", "content": content}], **kw)
    _record(msg)
    return msg.content[0].text


def _ask_json_live(prompt: str, model: type[T], max_tokens: int, timeout: float | None = None) -> T:
    if provider() == "gemini":
        from app.gemini import gemini_json
        return gemini_json(prompt, model, max_tokens)
    from app.claude import claude_json  # Claude Structured Outputs: reply always matches `model`
    return claude_json(prompt, model, max(max_tokens, 16000), timeout)


def ask_json(prompt: str, model: type[T], max_tokens: int = 8000, timeout: float | None = None) -> T:
    """Structured answer that always matches `model`. Cached on disk unless --cache off.
    timeout: for calls a person waits on (e.g. settings.llm_ui_timeout_s); None = the 2-minute default."""
    if provider() == "mock":
        return mock_json(model)
    return llm_cache.cached(prompt, model, lambda: _ask_json_live(prompt, model, max_tokens, timeout),
                            provider(), model_name())


def ask_image(png: bytes, prompt: str, max_tokens: int = 4000) -> str:
    """Read an image (e.g. a scanned page). Not cached."""
    if provider() == "mock":
        return MOCK_TEXT
    if provider() == "gemini":
        from app.gemini import gemini_image
        return gemini_image(png, prompt, max_tokens)
    img = base64.standard_b64encode(png).decode()
    with stage("llm.claude.image", LOG) as info:
        info.update(model=settings.anthropic_model)
        msg = _client().messages.create(
            model=settings.anthropic_model, max_tokens=max_tokens,
            messages=[{"role": "user", "content": [
                {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": img}},
                {"type": "text", "text": prompt},
            ]}],
        )
    _record(msg)
    return msg.content[0].text
