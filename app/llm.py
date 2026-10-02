"""Small LLM helpers. LLM_PROVIDER in .env picks Claude (anthropic) or Gemini (gemini).

ask("Summarize this", text)            -> str
ask_json(prompt, MyPydanticModel)      -> MyPydanticModel   (Claude Structured Outputs / Gemini JSON mode)
ask_image(png_bytes, "Transcribe...")  -> str
"""
import base64
import sys
import time
from typing import TypeVar

from pydantic import BaseModel

from app.config import settings


def _client():
    from app.claude import client  # 2-minute time limit, one retry
    return client()


def _gemini() -> bool:
    return settings.llm_provider == "gemini"


def ask(prompt: str, text: str = "", system: str | None = None, max_tokens: int = 2000) -> str:
    content = f"{prompt}\n\n{text}" if text else prompt
    if _gemini():
        from app.gemini import gemini_text
        return gemini_text(f"{system}\n\n{content}" if system else content, max_tokens)
    kw = {"system": system} if system else {}
    print(f"[claude] ask {settings.anthropic_model}...", file=sys.stderr, flush=True)
    start = time.monotonic()
    try:
        msg = _client().messages.create(model=settings.anthropic_model, max_tokens=max_tokens,
                                        messages=[{"role": "user", "content": content}], **kw)
    finally:
        print(f"[claude] took {time.monotonic() - start:.1f} s", file=sys.stderr, flush=True)
    return msg.content[0].text


T = TypeVar("T", bound=BaseModel)


def ask_json(prompt: str, model: type[T], max_tokens: int = 8000) -> T:
    if _gemini():
        from app.gemini import gemini_json
        return gemini_json(prompt, model, max_tokens)
    from app.claude import claude_json  # Claude Structured Outputs: reply always matches `model`
    return claude_json(prompt, model, max(max_tokens, 16000))


def ask_image(png: bytes, prompt: str, max_tokens: int = 4000) -> str:
    if _gemini():
        from app.gemini import gemini_image
        return gemini_image(png, prompt, max_tokens)
    img = base64.standard_b64encode(png).decode()
    msg = _client().messages.create(
        model=settings.anthropic_model, max_tokens=max_tokens,
        messages=[{"role": "user", "content": [
            {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": img}},
            {"type": "text", "text": prompt},
        ]}],
    )
    return msg.content[0].text
