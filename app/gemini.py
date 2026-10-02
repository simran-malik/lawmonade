"""Gemini helpers (Google's `google-genai` package). Free tier: key from aistudio.google.com.
NOTE: on the free tier Google may use your prompts to improve its products. Use fake data only.

gemini_text("Summarize this ...")          -> str
gemini_json("Extract ...", MyModel)        -> MyModel   (JSON mode + Pydantic check, 1 retry)
gemini_image(png_bytes, "Transcribe ...")  -> str
"""
import json
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from app import usage
from app.config import settings
from app.jsonutil import parse_json  # noqa: F401  (kept here so old imports work)

T = TypeVar("T", bound=BaseModel)


TIMEOUT_MS = 90_000   # give up after 90 s instead of hanging


_CLIENT = None


def _client():
    """Create the Gemini client once and keep it. A client made and dropped in the same line
    gets closed before the request is sent ("client has been closed")."""
    global _CLIENT
    from google import genai
    from google.genai import types

    if not settings.gemini_api_key:
        raise RuntimeError("GEMINI_API_KEY is empty (set it in .env)")
    if _CLIENT is None:
        _CLIENT = genai.Client(api_key=settings.gemini_api_key, http_options=types.HttpOptions(timeout=TIMEOUT_MS))
    return _CLIENT


def _config(json_mode: bool = False, max_tokens: int = 8000):
    from google.genai import types

    kw = {
        # Gemini 2.5 "thinks" first and that counts toward this limit, so never set it tiny.
        "max_output_tokens": max(max_tokens, 1024),
        "temperature": 0,
        # We never give Gemini tools, so turn off auto tool-calling (also silences the AFC warning).
        "automatic_function_calling": types.AutomaticFunctionCallingConfig(disable=True),
    }
    if json_mode:
        kw["response_mime_type"] = "application/json"
    return types.GenerateContentConfig(**kw)


def _used(r):
    """Log token use for one Gemini reply (thinking tokens count as output) and pass the reply on."""
    m = getattr(r, "usage_metadata", None)
    out = (getattr(m, "candidates_token_count", 0) or 0) + (getattr(m, "thoughts_token_count", 0) or 0)
    usage.record("gemini", settings.gemini_model, getattr(m, "prompt_token_count", 0) or 0, out)
    return r


def _text(r) -> str:
    if not r.text:
        reason = getattr((getattr(r, "candidates", None) or [None])[0], "finish_reason", "unknown")
        raise RuntimeError(f"Gemini returned no text (finish_reason={reason}). Try a larger max_tokens.")
    return r.text


def gemini_text(prompt: str, max_tokens: int = 4000) -> str:
    r = _client().models.generate_content(model=settings.gemini_model, contents=prompt,
                                          config=_config(max_tokens=max_tokens))
    return _text(_used(r))


def gemini_image(png: bytes, prompt: str, max_tokens: int = 4000) -> str:
    from google.genai import types

    r = _client().models.generate_content(
        model=settings.gemini_model,
        contents=[types.Part.from_bytes(data=png, mime_type="image/png"), prompt],
        config=_config(max_tokens=max_tokens),
    )
    return _text(_used(r))


def gemini_json(prompt: str, model: type[T], max_tokens: int = 8000) -> T:
    schema = json.dumps(model.model_json_schema())
    full = f"{prompt}\n\nReply with JSON only. It must match this JSON schema:\n{schema}"
    client = _client()
    text = _text(_used(client.models.generate_content(model=settings.gemini_model, contents=full,
                                                config=_config(True, max_tokens))))
    try:
        return parse_json(text, model)
    except (ValidationError, json.JSONDecodeError) as e:   # one retry with the error shown
        fix = f"{full}\n\nYour last answer was invalid:\n{e}\nReturn corrected JSON only."
        text = _text(_used(client.models.generate_content(model=settings.gemini_model, contents=fix,
                                                    config=_config(True, max_tokens))))
        return parse_json(text, model)
