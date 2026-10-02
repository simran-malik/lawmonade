from app.config import settings
from app.grounding import check_quote, normalize

PAGE = "PLEASE TAKE NOTICE that on December 3, 2026, at 8:30 a.m., in Department C-65"


def words(text, conf=95):
    return [{"text": t, "conf": conf, "box": (0, 0, 0, 0)} for t in text.split()]


def test_settings_load():
    assert settings.ocr_min_conf > 0


def test_normalize():
    assert normalize("8:30 a.m., $25,000") == ["8:30", "am", "$25000"]


def test_quote_verified_despite_case_and_punctuation():
    assert check_quote("on december 3 2026 at 8:30 am", words(PAGE))["verdict"] == "verified"


def test_wrong_date_is_hallucination():
    assert check_quote("on December 8, 2026, at 8:30 a.m.", words(PAGE))["verdict"] == "hallucination"


def test_wrong_date_on_bad_scan_needs_review():
    assert check_quote("on December 8, 2026, at 8:30 a.m.", words(PAGE, conf=40))["verdict"] == "needs_review"


def test_quote_not_on_page():
    assert check_quote("the trial is set for March 15", words(PAGE))["verdict"] == "hallucination"
