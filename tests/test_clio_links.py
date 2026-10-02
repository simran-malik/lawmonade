"""Links into Clio's web app (no network needed)."""
from app.clio import item_link


def test_links():
    assert item_link("Task", 7, 99, "x")[0].endswith("/nc/#/matters/7/tasks?taskId=99")
    assert item_link("Document", 7, 5, "x")[0].endswith("/nc/#/documents/5/details")
    url, hint = item_link("Note", 7, 1, "Intake summary")
    assert url.endswith('/notes?query=%7B%22value%22:%22Intake%20summary%22%7D') and hint == ""
    url, hint = item_link("Calendar", 7, 1, "Orthopedic IME")
    assert url.endswith("/matters/7/calendar") and hint == "Orthopedic IME"
