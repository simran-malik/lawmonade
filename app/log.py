"""Logging for the whole app: one setup call, one line per stage, secrets masked.

setup()                        -> call once at the top of each entry point (UI, API, scripts)
get("clio")                    -> logger named "lawmonade.clio"
with stage("clio.notes") as s:  -> logs "[clio.notes] 1.1s, items=9" when the block ends
    s["items"] = 9
Level: LOG_LEVEL in .env, or  bash run.sh ui --log-level DEBUG

Never log API keys, tokens, document text or full email addresses. The filter below masks
the common ones anyway, as a safety net.
"""
import contextvars
import logging
import re
import secrets
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager

ROOT = "lawmonade"
FORMAT = "%(asctime)s %(levelname)-7s %(run_id)s %(name)s  %(message)s"
_RUN = contextvars.ContextVar("run_id", default="-")


def new_run() -> str:
    """Start a new run id (e.g. one case load) so all its log lines can be found together."""
    rid = secrets.token_hex(3)
    _RUN.set(rid)
    return rid

# (pattern, replacement). Order matters: specific patterns first.
_MASKS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"sk-ant-[A-Za-z0-9_\-]+"), "sk-ant-***"),                       # Anthropic key
    (re.compile(r"AIza[0-9A-Za-z_\-]{20,}"), "AIza***"),                          # Google API key
    (re.compile(r"(?i)bearer\s+[A-Za-z0-9._~+/\-]+=*"), "Bearer ***"),            # OAuth tokens
    (re.compile(r"(?i)basic\s+[A-Za-z0-9+/]{8,}=*"), "Basic ***"),               # Twilio-style basic auth
    (re.compile(r"hooks\.slack\.com/services/[A-Za-z0-9/]+"), "hooks.slack.com/services/***"),
    (re.compile(r"(?i)\b(access_token|refresh_token|token|share|secret|password|api_key|auth_token)"
                r"([=:]\s*)([^&\s,'\"]+)"), r"\1\2***"),                         # key=value / key: value
    (re.compile(r"\b[\w.+-]+@([\w-]+(?:\.[\w-]+)+)\b"), r"***@\1"),               # keep only the domain
]


def redact(text: str) -> str:
    """Mask secrets and email addresses in one log line."""
    for pattern, repl in _MASKS:
        text = pattern.sub(repl, text)
    return text


def short(secret: str, keep: int = 6) -> str:
    """First few characters of an id-like secret (e.g. a share token), safe to log."""
    s = str(secret or "")
    return s[:keep] + "…" if len(s) > keep else "***"


class RedactFilter(logging.Filter):
    """Applies redact() to every record that reaches our handler (ours and libraries'), and adds the run id."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg, record.args = redact(record.getMessage()), None
        record.run_id = getattr(record, "run_id", None) or _RUN.get()
        return True


def setup(level: str | None = None) -> None:
    """Configure logging once. Safe to call again (Streamlit re-runs the script on every click)."""
    from app.config import settings

    lvl = (level or settings.log_level or "INFO").upper()
    root = logging.getLogger()
    handler = next((h for h in root.handlers if getattr(h, "_lawmonade", False)), None)
    if handler is None:
        handler = logging.StreamHandler(sys.stderr)
        handler._lawmonade = True
        handler.setFormatter(logging.Formatter(FORMAT, datefmt="%H:%M:%S"))
        handler.addFilter(RedactFilter())
        root.addHandler(handler)
    root.setLevel(logging.WARNING)                 # libraries: warnings only
    logging.getLogger(ROOT).setLevel(lvl)          # our code: the chosen level


def get(name: str) -> logging.Logger:
    """Logger for one part of the app, e.g. get("clio") -> "lawmonade.clio"."""
    return logging.getLogger(f"{ROOT}.{name}")


def _fmt(info: dict) -> str:
    return "".join(f", {k}={v}" for k, v in info.items() if v is not None)


@contextmanager
def stage(name: str, logger: logging.Logger | None = None) -> Iterator[dict]:
    """Time a block and log one line when it ends. Put counts in the yielded dict.

    Success -> INFO  "[name] 2.4s, items=3"
    Failure -> WARNING "[name] 2.4s FAILED (ValueError)" and the error is re-raised.
    """
    lg = logger or get("stage")
    info: dict = {}
    start = time.monotonic()
    try:
        yield info
    except BaseException as e:
        lg.warning("[%s] %.1fs FAILED (%s)%s", name, time.monotonic() - start, type(e).__name__, _fmt(info))
        raise
    lg.info("[%s] %.1fs%s", name, time.monotonic() - start, _fmt(info))
