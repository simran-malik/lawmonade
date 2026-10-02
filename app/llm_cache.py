"""Save AI answers on disk so the same question is never paid for twice.

cached(prompt, MyModel, call, provider, model_name) -> MyModel
  key  = sha256 of (provider, model name, schema, prompt). The prompt already holds the case text,
         so a changed case or a changed schema means a new key (no stale answers).
  file = data/cache/llm/<key>.json, written safely (temp file + rename).

LLM_CACHE (or --cache) picks the mode:
  on   use a saved answer if there is one, otherwise call the AI and save the answer (default)
  off  always call the AI, save nothing
  only never call the AI; no saved answer -> CacheMiss (offline demo: run once online with "on" first)
"""
import hashlib
import json
import os
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from app.config import settings
from app.log import get, stage
from app.snapshot import now_iso

LOG = get("llm")
T = TypeVar("T", bound=BaseModel)
MODES = ("on", "off", "only")


class CacheMiss(RuntimeError):
    """LLM_CACHE=only and there is no saved answer for this request."""

    def __init__(self, schema: str):
        super().__init__(f"No saved AI answer for this {schema} yet (cache mode is 'only'). "
                         "Run it once online with --cache on, then the offline demo will work.")


def key(provider: str, model_name: str, schema: type[BaseModel], prompt: str) -> str:
    """Stable hash of everything that changes the answer."""
    parts = [provider, model_name, schema.__name__, schema.model_json_schema(), prompt]
    return hashlib.sha256(json.dumps(parts, sort_keys=True, default=str).encode()).hexdigest()


def _path(k: str) -> Path:
    return settings.llm_cache_dir / f"{k}.json"


def load(k: str, schema: type[T]) -> T | None:
    """Saved answer, or None if missing or no longer valid for the schema."""
    p = _path(k)
    if not p.exists():
        return None
    try:
        return schema.model_validate(json.loads(p.read_text())["output"])
    except (ValueError, KeyError, ValidationError):
        LOG.warning("[llm.cache] ignoring unreadable entry %s", k[:12])
        return None


def save(k: str, value: BaseModel, provider: str, model_name: str) -> Path:
    """Write one answer (never a half-written file)."""
    p = _path(k)
    p.parent.mkdir(parents=True, exist_ok=True)
    entry = {"key": k, "provider": provider, "model": model_name, "schema": type(value).__name__,
             "created_at": now_iso(), "output": value.model_dump(mode="json")}
    fd, tmp = tempfile.mkstemp(dir=p.parent, suffix=".tmp")
    with os.fdopen(fd, "w") as f:
        json.dump(entry, f, indent=1)
    os.replace(tmp, p)
    return p


def cached(prompt: str, schema: type[T], call: Callable[[], T], provider: str, model_name: str,
           mode: str | None = None) -> T:
    """Return a saved answer or call the AI (see module docstring for the modes)."""
    mode = (mode or settings.llm_cache or "on").lower()
    if mode not in MODES:
        raise ValueError(f"LLM_CACHE must be one of {', '.join(MODES)} (got {mode!r})")
    k = key(provider, model_name, schema, prompt)
    with stage("llm", LOG) as info:
        info.update(schema=schema.__name__, provider=provider)
        if mode != "off":
            hit = load(k, schema)
            if hit is not None:
                info["cache"] = "hit"
                return hit
        if mode == "only":
            info["cache"] = "miss"
            raise CacheMiss(schema.__name__)
        info["cache"] = "miss" if mode == "on" else "off"
        value = call()
        if mode == "on":
            save(k, value, provider, model_name)
        return value
