import logging

import pytest

from app import log


def test_redact_masks_keys_tokens_and_emails():
    line = ("key sk-ant-api03-abcDEF_123 Bearer eyJhbGciOi.abc-def "
            "https://hooks.slack.com/services/T0/B0/xyz ?share=Zt9kQ2abcdef&x=1 "
            "access_token=abc123 to dr.lee@clinic-west.com")
    out = log.redact(line)
    for secret in ("abcDEF_123", "eyJhbGciOi", "T0/B0/xyz", "Zt9kQ2abcdef", "abc123", "dr.lee"):
        assert secret not in out
    assert "***@clinic-west.com" in out and "x=1" in out


def test_short_keeps_only_a_prefix():
    assert log.short("Zt9kQ2abcdefghij") == "Zt9kQ2…"
    assert log.short("") == "***"


def test_stage_logs_time_and_counts(caplog):
    caplog.set_level(logging.INFO, logger="lawmonade")
    with log.stage("clio.notes") as info:
        info["items"] = 9
    msg = caplog.records[-1].getMessage()
    assert msg.startswith("[clio.notes] ") and msg.endswith("s, items=9")


def test_stage_logs_failure_and_reraises(caplog):
    caplog.set_level(logging.INFO, logger="lawmonade")
    with pytest.raises(ValueError):
        with log.stage("extract"):
            raise ValueError("boom")
    rec = caplog.records[-1]
    assert rec.levelno == logging.WARNING and "FAILED (ValueError)" in rec.getMessage()


def test_setup_is_idempotent_and_filter_redacts(capsys):
    log.setup("DEBUG")
    log.setup("DEBUG")
    ours = [h for h in logging.getLogger().handlers if getattr(h, "_lawmonade", False)]
    assert len(ours) == 1
    rec = logging.LogRecord("lawmonade.t", logging.INFO, __file__, 1, "token=%s", ("supersecret",), None)
    ours[0].filter(rec)
    assert rec.getMessage() == "token=***"
