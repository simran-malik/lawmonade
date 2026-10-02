"""Turn an AI's text reply into a checked Pydantic object."""
import json
import re
from typing import TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


def parse_json(text: str, model: type[T]) -> T:
    """Accepts plain JSON, JSON in ``` fences, or JSON with words around it."""
    t = (text or "").strip()
    m = re.search(r"```(?:json)?\s*(.*?)```", t, re.S)
    if m:
        t = m.group(1).strip()
    elif not t.startswith(("{", "[")):
        start, end = t.find("{"), t.rfind("}")
        if start != -1 and end > start:
            t = t[start:end + 1]
    return model.model_validate(json.loads(t))
