"""Put a case's tasks and calendar entries on the firm's Google Calendar. Clio is never changed.

Setup, once:  bash run.sh gcal   (Google sign-in with credentials.json -> token_gcal.json)
Calendar:     GOOGLE_CALENDAR_ID in .env ("primary" = the signed-in account's own calendar)

add(snap, item, by)       one task or calendar entry -> one Google event. Returns {"status": "added" | "already", ...}
pending(snap)             the items "Add all" would add: dated, today or later, open tasks only, not added yet
added(matter_id)          {item key: row} for everything already on the calendar (from our own SQLite store)

No duplicates, even on a double click, a retry or two people pressing at once: each item gets a FIXED Google event id
(a hash of calendar + case + item). Google refuses a second event with the same id (409), and we count that as
"already added". That is also why the insert is safe to retry.
"""
import hashlib
from datetime import datetime, timedelta

from app import retry, store
from app.config import ROOT, settings
from app.log import get, stage
from app.share import firm_now, is_open, local_date

LOG = get("gcal")

SCOPES = ["https://www.googleapis.com/auth/calendar.events"]
TOKEN = ROOT / "token_gcal.json"
KINDS = ("Task", "Calendar")
EVENT_MINUTES = 60          # Clio calendar entry without an end time


class CalendarError(Exception):
    def __init__(self, message: str, fix: str):
        super().__init__(message)
        self.message, self.fix = message, fix


def ready() -> bool:
    return TOKEN.exists()


def _service(interactive: bool = False):
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    creds = Credentials.from_authorized_user_file(str(TOKEN), SCOPES) if TOKEN.exists() else None
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        elif interactive:
            from google_auth_oauthlib.flow import InstalledAppFlow
            flow = InstalledAppFlow.from_client_secrets_file(str(ROOT / "credentials.json"), SCOPES)
            creds = flow.run_local_server(port=0)
        else:
            raise CalendarError("Google Calendar isn't set up yet.",
                                "In Terminal run: bash run.sh gcal  (one-time Google sign-in).")
        TOKEN.write_text(creds.to_json())
    return build("calendar", "v3", credentials=creds, cache_discovery=False)


# ---------- which items, and what the event looks like ----------
def kind(item: dict) -> str:
    return item.get("kind") or item["src"]["kind"]


def key(item: dict) -> str:
    """'Task:123' / 'Calendar:456': one row per item in our store."""
    return f"{kind(item)}:{item['id']}"


def event_id(matter_id, item: dict, calendar_id: str | None = None) -> str:
    """Google event ids may only use 0-9 and a-v; hex fits."""
    raw = f"{calendar_id or settings.google_calendar_id}|{matter_id}|{key(item)}"
    return "lm" + hashlib.sha256(raw.encode()).hexdigest()[:40]


def can_add(item: dict) -> bool:
    """Has a usable date and is a task or calendar entry (the per-item button shows for these)."""
    return kind(item) in KINDS and local_date(item.get("date")) is not None


def _timed(value) -> datetime | None:
    """A Clio date/time with a real time of day, else None (a date-only value means an all-day event)."""
    s = str(value or "")
    if "T" not in s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def event_body(snap: dict, item: dict) -> dict:
    m = snap["matter"]
    k = kind(item)
    case = " · ".join(x for x in (m.get("number"), m.get("client")) if x)
    url = item["src"].get("url") or m.get("url") or ""
    hint = item["src"].get("hint")
    lines = [(item.get("text") or "").strip(), "",
             f"Case: {case}" if case else "",
             f"From Clio: {item['src']['label']}",
             f"Open in Clio: {url}" + (f'  (then search "{hint}")' if hint else "") if url else "",
             "Added by Law-monade. Changes in Clio are not copied here."]
    body = {"id": event_id(m["id"], item),
            "summary": f"{'Task due: ' if k == 'Task' else ''}{item.get('title') or '(no title)'}"
                       + (f" ({m['client']})" if m.get("client") else ""),
            "description": "\n".join(x for x in lines).strip(),
            "extendedProperties": {"private": {"lm_matter": str(m["id"]), "lm_item": key(item)}}}
    if url.startswith("http"):
        body["source"] = {"title": "Clio", "url": url}
    start = _timed(item.get("date")) if k == "Calendar" else None     # a task due date is a day, not a time
    if start:
        end = _timed(item.get("end")) or start + timedelta(minutes=EVENT_MINUTES)
        if end <= start:
            end = start + timedelta(minutes=EVENT_MINUTES)
        body["start"] = {"dateTime": start.isoformat(), "timeZone": settings.timezone}
        body["end"] = {"dateTime": end.isoformat(), "timeZone": settings.timezone}
    else:
        day = local_date(item.get("date"))
        body["start"] = {"date": day.isoformat()}
        body["end"] = {"date": (day + timedelta(days=1)).isoformat()}
    return body


def added(matter_id) -> dict:
    return store.calendar_adds(matter_id, settings.google_calendar_id)


def pending(snap: dict, done: dict | None = None) -> list[dict]:
    """What "Add all" adds: tasks and calendar entries dated today or later, open tasks only, not added yet.
    Past entries and finished tasks can still be added one by one."""
    done = added(snap["matter"]["id"]) if done is None else done
    today = firm_now().date()
    out = []
    for group in ("tasks", "calendar"):
        for it in snap.get(group, []):
            if not can_add(it) or key(it) in done or local_date(it["date"]) < today:
                continue
            if kind(it) == "Task" and not is_open(it):
                continue
            out.append(it)
    return sorted(out, key=lambda it: local_date(it["date"]))


# ---------- add ----------
def add(snap: dict, item: dict, by: str = "", service=None) -> dict:
    """Put one item on the calendar (or find it already there). Saves it in our store either way."""
    if not can_add(item):
        raise CalendarError("This entry has no date, so it can't go on a calendar.", "Add a date in Clio first.")
    mid = snap["matter"]["id"]
    cal = settings.google_calendar_id
    body = event_body(snap, item)
    svc = service or _service()

    def once():
        return svc.events().insert(calendarId=cal, body=body).execute()

    status = "added"
    try:
        with stage("gcal.add", LOG):
            ev = retry.run(once, safe_to_repeat=True, what="gcal insert", to_transient=retry.from_google_error)
    except Exception as e:
        code = getattr(getattr(e, "resp", None), "status", None)
        if code == 409:               # this exact event already exists (earlier click, retry, or a colleague)
            status, ev = "already", {"id": body["id"], "htmlLink": ""}
        elif code in (401, 403):
            raise CalendarError("Google Calendar refused the request.",
                                "Run bash run.sh gcal again to sign in, and check GOOGLE_CALENDAR_ID in .env.") from None
        elif code == 404:
            raise CalendarError(f'Google can\'t find the calendar "{cal}".',
                                "Fix GOOGLE_CALENDAR_ID in .env (\"primary\" is your own calendar).") from None
        elif type(e).__name__ == "RefreshError":
            raise CalendarError("Your Google sign-in has expired.", "In Terminal run: bash run.sh gcal") from None
        elif isinstance(e, CalendarError):
            raise
        else:
            LOG.warning("[gcal.add] %s failed: %s", key(item), type(e).__name__)
            raise CalendarError("Couldn't reach Google Calendar.", "Check your internet connection, then try again.") from None
    store.save_calendar_add(mid, key(item), cal, ev["id"], ev.get("htmlLink", ""), by)
    return {"status": status, "event_id": ev["id"], "link": ev.get("htmlLink", "")}


def add_many(snap: dict, items: list[dict], by: str = "", on_step=None) -> dict:
    """Add several. Keeps going past one bad item; stops if Google sign-in or the calendar itself is the problem.
    on_step(i, n, item) lets the screen show progress."""
    out = {"added": 0, "already": 0, "failed": []}
    svc = _service()
    for i, it in enumerate(items):
        if on_step:
            on_step(i, len(items), it)
        try:
            r = add(snap, it, by, service=svc)
            out[r["status"]] += 1
        except CalendarError as e:
            out["failed"].append({"title": it.get("title") or "(no title)", "error": e.message, "fix": e.fix})
            if "sign" in e.fix or "GOOGLE_CALENDAR_ID" in e.fix:     # every other item would fail the same way
                break
    return out


if __name__ == "__main__":      # bash run.sh gcal -> one-time sign-in
    _service(interactive=True)
    print("Google Calendar is set up. Events go to calendar:", settings.google_calendar_id)
