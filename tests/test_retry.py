import io
import urllib.error

import pytest
import requests

from app import retry
from app.retry import Transient


def flaky(*outcomes):
    """fn that raises/returns the given outcomes in order; .calls counts calls."""
    seq = list(outcomes)

    def fn():
        fn.calls += 1
        out = seq.pop(0)
        if isinstance(out, BaseException):
            raise out
        return out
    fn.calls = 0
    return fn


def run(fn, safe=True, **kw):
    waits = []
    out = retry.run(fn, safe_to_repeat=safe, what="test", sleep=waits.append, **kw)
    return out, waits


def test_429_then_success_retries_with_backoff():
    fn = flaky(Transient("status", 429), Transient("status", 503), "ok")
    out, waits = run(fn)
    assert out == "ok" and fn.calls == 3
    assert 0.5 <= waits[0] <= 0.625 and 1.0 <= waits[1] <= 1.25


def test_4xx_is_never_retried():
    fn = flaky(urllib.error.HTTPError("u", 400, "bad", {}, io.BytesIO()), "ok")
    with pytest.raises(urllib.error.HTTPError):
        run(fn, to_transient=retry.from_urllib_error)
    assert fn.calls == 1


def test_send_is_not_retried_after_timeout_or_500():
    for err in (TimeoutError(), Transient("status", 500)):
        fn = flaky(err, "ok")
        with pytest.raises(type(err)):
            run(fn, safe=False, to_transient=retry.from_urllib_error)
        assert fn.calls == 1


def test_send_is_retried_when_nothing_was_sent():
    fn = flaky(urllib.error.URLError("refused"), Transient("status", 429), "sent")
    out, _ = run(fn, safe=False, to_transient=retry.from_urllib_error)
    assert out == "sent" and fn.calls == 3


def test_safe_get_retries_read_timeout():
    fn = flaky(requests.ReadTimeout(), "ok")
    out, _ = run(fn, to_transient=retry.from_requests_error)
    assert out == "ok" and fn.calls == 2


def test_gives_up_after_attempts_and_raises_original():
    fn = flaky(*[requests.ConnectionError()] * 3)
    with pytest.raises(requests.ConnectionError):
        run(fn, to_transient=retry.from_requests_error)
    assert fn.calls == 3


def test_long_retry_after_is_not_waited():
    fn = flaky(Transient("status", 429, retry_after=60), "ok")
    with pytest.raises(Transient):
        run(fn)
    assert fn.calls == 1


def test_from_status_reads_retry_after():
    t = retry.from_status(429, {"Retry-After": "2"})
    assert t.status == 429 and t.retry_after == 2.0
    assert retry.from_status(404) is None and retry.from_status(200) is None


def test_clio_get_retries_then_explains_429(monkeypatch):
    from app import clio
    from app.config import settings

    class Resp:
        def __init__(self, code):
            self.status_code, self.headers = code, {}
    codes = [503, 200]
    monkeypatch.setattr(settings, "clio_access_token", "t")
    monkeypatch.setattr(clio.requests, "get", lambda *a, **k: Resp(codes.pop(0)))
    monkeypatch.setattr(retry.time, "sleep", lambda s: None)
    assert clio._get("https://x/api").status_code == 200

    monkeypatch.setattr(clio.requests, "get", lambda *a, **k: Resp(429))
    with pytest.raises(clio.ClioError, match="slow down"):
        clio._get("https://x/api")
