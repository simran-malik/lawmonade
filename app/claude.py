"""Claude helpers.

client()                             -> Anthropic client with a 2-minute time limit
claude_json("Extract ...", MyModel)  -> MyModel   (Structured Outputs: reply always matches the model)
Docs: https://platform.claude.com/docs/en/build-with-claude/structured-outputs
"""
from typing import TypeVar

from pydantic import BaseModel

from app import usage
from app.config import settings
from app.log import get, stage

LOG = get("claude")

T = TypeVar("T", bound=BaseModel)
TIMEOUT_S = 120   # give up after 2 minutes instead of hanging the screen


def client(timeout: float | None = None):
    """Anthropic client. Default: 2-minute limit + one retry (scripts, digests).
    With a timeout (calls made while a person waits on the screen): that limit and no retry."""
    import anthropic

    if not settings.anthropic_api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is empty in .env")
    if timeout:
        return anthropic.Anthropic(api_key=settings.anthropic_api_key, timeout=timeout, max_retries=0)
    # max_retries=1: one quick retry on a network blip, not several long ones
    return anthropic.Anthropic(api_key=settings.anthropic_api_key, timeout=TIMEOUT_S, max_retries=1)


def claude_json(prompt: str, model: type[T], max_tokens: int = 16000, timeout: float | None = None) -> T:
    import anthropic

    c = client(timeout)
    if not hasattr(c.messages, "parse"):
        raise RuntimeError("Your anthropic package is too old for Structured Outputs. "
                           "Run: uv sync --upgrade-package anthropic")
    try:
        with stage("llm.claude", LOG) as info:
            info.update(model=settings.anthropic_model, schema=model.__name__)
            # The SDK turns the Pydantic model into a JSON schema (moving rules Claude can't enforce,
            # like min/max, into descriptions), and checks the reply against the full model.
            r = c.messages.parse(
                model=settings.anthropic_model,
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}],
                output_format=model,
            )
            info.update(stop=r.stop_reason)
        u = getattr(r, "usage", None)
        usage.record("anthropic", settings.anthropic_model, getattr(u, "input_tokens", 0), getattr(u, "output_tokens", 0))
    except anthropic.APITimeoutError:
        raise RuntimeError(f"Claude took longer than {timeout or TIMEOUT_S:.0f} s and was stopped. "
                           "Try again, or use --llm mock for the demo.") from None

    if r.stop_reason == "refusal":
        raise RuntimeError("Claude declined this request (stop_reason=refusal).")
    if r.stop_reason == "max_tokens":
        raise RuntimeError("Claude's answer was cut off (max_tokens). Try a shorter document or raise max_tokens.")
    if r.parsed_output is None:
        raise RuntimeError(f"Claude returned no structured answer (stop_reason={r.stop_reason}).")
    return r.parsed_output
