"""Retry temporary failures with exponential backoff. No extra packages.

run(fn, safe_to_repeat=True, what="clio GET", to_transient=from_requests_error)

Rules:
  - Retry only temporary problems: connection errors, timeouts, 429 and 5xx. Never other 4xx.
  - safe_to_repeat=False (sending email, SMS, Slack): retry only when we know nothing was sent:
    connection errors, 429 and 503. A timeout or a 500 might mean it WAS sent, so no retry
    (better one missing message, with a clear error, than a provider getting it twice).
  - Waits 0.5 s, 1 s, 2 s (+ up to 25% random), or the server's Retry-After.
    Gives up when the total wait would pass `budget_s`, so the screen never hangs.
After the last try the ORIGINAL error is raised, so callers' existing error messages still work.
"""
import random
import socket
import time
from collections.abc import Callable
from typing import TypeVar

from app.log import get

LOG = get("retry")
R = TypeVar("R")

RETRY_STATUS_SAFE = {429, 500, 502, 503, 504}
RETRY_STATUS_SEND = {429, 503}


class Transient(Exception):
    """A failure that may go away if we try again.

    kind: "status" (HTTP code in `status`), "connect" (never reached the server, safe to resend)
          or "timeout" (no answer; the server may already have acted on it).
    """

    def __init__(self, kind: str, status: int | None = None, retry_after: float | None = None):
        super().__init__(f"{kind}{f' {status}' if status else ''}")
        self.kind, self.status, self.retry_after = kind, status, retry_after


def should_retry(t: Transient, safe_to_repeat: bool) -> bool:
    """Decide from the kind of failure and whether repeating the call is harmless."""
    if t.kind == "connect":
        return True
    if t.kind == "timeout":
        return safe_to_repeat
    return t.status in (RETRY_STATUS_SAFE if safe_to_repeat else RETRY_STATUS_SEND)


def delay(attempt: int, retry_after: float | None = None, base: float = 0.5,
          rand: Callable[[], float] = random.random) -> float:
    """Seconds to wait before try number attempt+1 (attempt starts at 1)."""
    if retry_after is not None:
        return max(0.0, retry_after)
    return base * 2 ** (attempt - 1) * (1 + 0.25 * rand())


def parse_retry_after(value) -> float | None:
    """Retry-After header in seconds. HTTP-date values are ignored (we fall back to backoff)."""
    try:
        return float(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def from_status(status: int, headers=None) -> Transient | None:
    """Transient for 429/5xx responses, None for anything else."""
    if status == 429 or 500 <= status < 600:
        return Transient("status", status, parse_retry_after((headers or {}).get("Retry-After")))
    return None


def run(fn: Callable[[], R], *, safe_to_repeat: bool, what: str,
        to_transient: Callable[[BaseException], Transient | None] | None = None,
        attempts: int = 3, base: float = 0.5, budget_s: float = 10.0,
        sleep: Callable[[float], None] = time.sleep) -> R:
    """Call fn(); on a temporary failure wait and try again (see module rules)."""
    waited = 0.0
    for attempt in range(1, attempts + 1):
        try:
            return fn()
        except Exception as e:
            t = e if isinstance(e, Transient) else (to_transient(e) if to_transient else None)
            if t is None or attempt == attempts or not should_retry(t, safe_to_repeat):
                raise
            wait = delay(attempt, t.retry_after, base)
            if waited + wait > budget_s:
                LOG.warning("[retry] %s: %s, not retrying (would wait %.0fs)", what, t, wait)
                raise
            LOG.warning("[retry] %s: %s, try %d/%d in %.1fs", what, t, attempt + 1, attempts, wait)
            sleep(wait)
            waited += wait
    raise AssertionError("unreachable")


# ---------- turn library errors into Transient (None = not temporary, don't retry) ----------
def from_requests_error(e: BaseException) -> Transient | None:
    """requests: ConnectTimeout/ConnectionError never reached the server; ReadTimeout might have."""
    import requests

    if isinstance(e, requests.ConnectionError):        # includes ConnectTimeout
        return Transient("connect")
    if isinstance(e, requests.Timeout):                # ReadTimeout
        return Transient("timeout")
    return None


def from_urllib_error(e: BaseException) -> Transient | None:
    """urllib (Slack, Twilio): HTTPError has a code; URLError = failed while connecting/sending;
    a bare timeout or reset comes while waiting for the answer."""
    import urllib.error

    if isinstance(e, urllib.error.HTTPError):
        return from_status(e.code, e.headers)
    if isinstance(e, urllib.error.URLError):
        return Transient("connect")
    return _from_socket_error(e)


def _from_socket_error(e: BaseException) -> Transient | None:
    """Refused = never reached the server. A timeout or reset may come after the server got the request."""
    if isinstance(e, ConnectionRefusedError):
        return Transient("connect")
    if isinstance(e, (TimeoutError, socket.timeout, ConnectionError)):
        return Transient("timeout")
    return None


def from_google_error(e: BaseException) -> Transient | None:
    """googleapiclient (Gmail): HttpError has resp.status; httplib2 raises its own connection errors."""
    status = getattr(getattr(e, "resp", None), "status", None)
    if status is not None and type(e).__name__ == "HttpError":
        return from_status(int(status), {"Retry-After": e.resp.get("retry-after")})
    if type(e).__name__ == "ServerNotFoundError":     # DNS failed: nothing was sent
        return Transient("connect")
    return _from_socket_error(e)
