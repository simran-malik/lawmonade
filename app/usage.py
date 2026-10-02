"""Token counts and cost for each AI call, so we can report "cost per case".

record("anthropic", "claude-sonnet-5-5", 8123, 940)   -> logs "[llm.usage] ... in=8123 out=940 cost=$0.0xx"
totals()                                              -> {"calls", "input_tokens", "output_tokens", "cost_usd"}
Prices come from .env (LLM_PRICE_IN_PER_MTOK / LLM_PRICE_OUT_PER_MTOK, USD per million tokens).
If they are not set, cost is shown as "n/a" (we never guess prices in code).
"""
from app.config import settings
from app.log import get

LOG = get("llm")
_TOTALS = {"calls": 0, "input_tokens": 0, "output_tokens": 0}


def cost_usd(input_tokens: int, output_tokens: int) -> float | None:
    """Dollar cost from the .env prices, or None if prices aren't set."""
    pin, pout = settings.llm_price_in_per_mtok, settings.llm_price_out_per_mtok
    if not (pin or pout):
        return None
    return (input_tokens * pin + output_tokens * pout) / 1_000_000


def _fmt(cost: float | None) -> str:
    return "n/a" if cost is None else f"${cost:.4f}"


def record(provider: str, model: str, input_tokens: int | None, output_tokens: int | None) -> None:
    """Add one call to the running totals and log it."""
    i, o = int(input_tokens or 0), int(output_tokens or 0)
    _TOTALS["calls"] += 1
    _TOTALS["input_tokens"] += i
    _TOTALS["output_tokens"] += o
    LOG.info("[llm.usage] %s %s in=%d out=%d cost=%s", provider, model, i, o, _fmt(cost_usd(i, o)))


def totals() -> dict:
    """Totals since start (or since reset()), with cost if prices are set."""
    return {**_TOTALS, "cost_usd": cost_usd(_TOTALS["input_tokens"], _TOTALS["output_tokens"])}


def reset() -> None:
    """Start counting again (e.g. at the start of one case)."""
    for k in _TOTALS:
        _TOTALS[k] = 0
