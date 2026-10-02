"""Deadlines for the daily digest: what is overdue, due soon and coming up, counted in the FIRM's time zone.

lists(snap, today=None) -> {
    "today": "2026-10-02",
    "overdue":      [item, ...]   open tasks whose due day has passed (newest first), up to LONG_OVERDUE days late
    "long_overdue": [item, ...]   open tasks more than DIGEST_LONG_OVERDUE_DAYS late (kept apart so they don't bury today's)
    "due_soon":     [item, ...]   open tasks and calendar entries today .. today + DIGEST_URGENT_DAYS
    "upcoming":     [item, ...]   after that, up to DIGEST_UPCOMING_DAYS
    "no_date": 3                  open tasks with no due date (counted, never called overdue)
    "sol": {...} | None           statute of limitations, if Clio has a real date for it
}
item = {kind, id, title, what, date (ISO day), nice, days (negative = late), src, contact | None}
contact = {name, role, kind: client | contact | staff, phone, email, sms_url, mail_url, draft}

Rules (edge cases):
  - Only OPEN tasks count. Calendar entries are never "overdue" (a past event is history, not a missed task).
  - Cancelled entries ("Cancelled: ...") are left out.
  - Dates are compared as the firm's local DAY ("2026-10-15T06:00:00Z" is Oct 14 in Los Angeles).
  - Who to text: the contact the task names (a provider, the insurer...), else the client if the task is about
    the client, else the staff member it's assigned to. A person sends the text; nothing is texted automatically.
"""
import re
from datetime import date, timedelta
from urllib.parse import quote

from app.config import settings
from app.share import firm_now, is_open, local_date, name_keys
from app.snapshot import nice_date

CANCELLED = re.compile(r"^\s*(cancel+ed|canceled|void)\b", re.I)
LIMITATIONS = re.compile(r"statute of limitations|limitations date|\bSOL\b", re.I)
FILED = re.compile(r"litigation|suit filed|lawsuit|trial|discovery", re.I)
MONEY = re.compile(r"\$\s?[\d,]+(?:\.\d+)?\s?(?:k|m|thousand|million)?\b", re.I)


# ---------- small helpers ----------
def what(title: str) -> str:
    """Short task text: 'By medical provider: McCulloch ... - Updated records' -> 'Updated records'. No $ amounts."""
    t = str(title or "").strip().split("\n")[0]
    if ":" in t.split(" - ", 1)[0] and " - " in t:
        t = t.split(" - ", 1)[1]
    return MONEY.sub("", t).strip(" -·") or "(no title)"


def phone(raw) -> str:
    """'(914) 555-0134' -> '+19145550134'. Too short or empty -> ''."""
    s = str(raw or "").strip()
    digits = re.sub(r"\D", "", s)
    if s.startswith("+") and 8 <= len(digits) <= 15:
        return "+" + digits
    if len(digits) == 10:
        return "+1" + digits
    if len(digits) == 11 and digits.startswith("1"):
        return "+" + digits
    return ""


def _first(name: str) -> str:
    parts = str(name or "").replace(",", " ").split()
    return parts[0] if parts else ""


def _text(it: dict) -> str:
    return f"{it.get('title', '')} {it.get('text', '')}".lower()


# ---------- who to contact ----------
def _match_contact(it: dict, contacts: list[dict]) -> dict | None:
    """The contact this item names. Best = most distinctive name words found; the first word must be one of them."""
    text, best, best_n = _text(it), None, 0
    for c in contacts:
        keys = name_keys(c.get("name", ""))
        if not keys or not re.search(rf"\b{re.escape(keys[0])}\b", text):
            continue
        n = sum(1 for k in keys if re.search(rf"\b{re.escape(k)}\b", text))
        if n > best_n:
            best, best_n = c, n
    return best


def draft(item_what: str, who: dict, client: str) -> str:
    """Short text message a person can edit before sending. Never amounts, never strategy."""
    firm = settings.firm_name
    if who["kind"] == "client":
        hi = f"Hi {_first(who['name'])}, " if _first(who["name"]) else "Hi, "
        return f"{hi}this is {firm}. A quick follow-up on your case: {item_what}. Could you reply or call us today? Thank you."
    if who["kind"] == "staff":
        return f"Hi {_first(who['name'])}, reminder: \"{item_what}\" on the {client or 'client'} case is overdue. Can you update it today?"
    return (f"Hello, this is {firm}, following up for our client {client or 'our client'}: {item_what}. "
            f"Could you reply with an update? Thank you.")


def contact_for(it: dict, snap: dict) -> dict | None:
    m = snap.get("matter") or {}
    c = _match_contact(it, snap.get("contacts") or [])
    client = m.get("client") or ""
    last = client.split()[-1].lower() if client.split() else ""
    if c:
        who = {"name": c.get("name", ""), "role": c.get("role", ""), "kind": "contact",
               "phone": phone(c.get("phone")), "email": c.get("email", "")}
    elif re.search(r"\bclient\b", _text(it)) or (last and re.search(rf"\b{re.escape(last)}\b", _text(it))):
        who = {"name": client, "role": "Client", "kind": "client",
               "phone": phone(m.get("client_phone")), "email": m.get("client_email", "")}
    elif it.get("assignee"):
        who = {"name": it["assignee"], "role": "Assigned to (firm staff)", "kind": "staff", "phone": "", "email": ""}
    else:
        return None
    who["draft"] = draft(it.get("what") or what(it.get("title")), who, client)
    who["sms_url"] = f"sms:{who['phone']}?&body={quote(who['draft'])}" if who["phone"] else ""
    who["mail_url"] = (f"mailto:{who['email']}?subject={quote('Follow-up: ' + (client or 'our client'))}"
                       f"&body={quote(who['draft'])}") if "@" in (who["email"] or "") else ""
    return who


# ---------- statute of limitations ----------
def sol(snap: dict, today: date) -> dict | None:
    """The SOL date: Clio's matter field if it holds a real date, else a task or calendar entry named for it.
    (Clio sometimes returns a reference object instead of a date; that is not treated as a date.)"""
    m = snap.get("matter") or {}
    raw, where = m.get("sol_date"), "Clio statute of limitations field"
    d = local_date(raw) if isinstance(raw, str) else None
    if d is None:
        for k in ("calendar", "tasks"):
            hit = next((x for x in snap.get(k, []) if LIMITATIONS.search(x.get("title") or "")
                        and local_date(x.get("date"))), None)
            if hit:
                d, where = local_date(hit.get("date")), hit["src"]["label"]
                break
    if d is None:
        return None
    days = (d - today).days
    filed = bool(FILED.search(m.get("stage") or ""))
    open_ = (m.get("status") or "open").lower() not in ("closed", "archived")
    urgent = open_ and ((0 <= days <= settings.digest_sol_warn_days) or (days < 0 and not filed))
    return {"date": d.isoformat(), "nice": d.strftime("%b %-d, %Y"), "days": days, "filed": filed,
            "urgent": urgent, "source": where}


# ---------- the lists ----------
def _item(it: dict, kind: str, d: date, today: date, snap: dict) -> dict:
    out = {"kind": kind, "id": str(it.get("id")), "title": it.get("title") or "(no title)", "what": what(it.get("title")),
           "date": d.isoformat(), "nice": d.strftime("%a %b %-d"), "days": (d - today).days,
           "src": {k: it.get("src", {}).get(k, "") for k in ("label", "url", "hint")}}
    out["contact"] = contact_for(out | {"text": it.get("text", ""), "assignee": it.get("assignee")}, snap) \
        if kind == "Task" else None
    return out


def lists(snap: dict, today: date | None = None) -> dict:
    today = today or firm_now().date()
    soon_end = today + timedelta(days=settings.digest_urgent_days)
    up_end = today + timedelta(days=settings.digest_upcoming_days)
    out = {"today": today.isoformat(), "overdue": [], "long_overdue": [], "due_soon": [], "upcoming": [], "no_date": 0}
    for t in snap.get("tasks", []):
        if not is_open(t) or CANCELLED.search(t.get("title") or ""):
            continue
        d = local_date(t.get("date"))
        if d is None:
            out["no_date"] += 1
            continue
        if d < today:
            late = (today - d).days
            out["long_overdue" if late > settings.digest_long_overdue_days else "overdue"].append(
                _item(t, "Task", d, today, snap))
        elif d <= soon_end:
            out["due_soon"].append(_item(t, "Task", d, today, snap))
        elif d <= up_end:
            out["upcoming"].append(_item(t, "Task", d, today, snap))
    for e in snap.get("calendar", []):
        d = local_date(e.get("date"))
        if d is None or d < today or CANCELLED.search(e.get("title") or ""):
            continue
        if d <= soon_end:
            out["due_soon"].append(_item(e, "Calendar", d, today, snap))
        elif d <= up_end:
            out["upcoming"].append(_item(e, "Calendar", d, today, snap))
    out["overdue"].sort(key=lambda x: x["days"], reverse=True)          # most recently due first
    out["long_overdue"].sort(key=lambda x: x["days"], reverse=True)
    out["due_soon"].sort(key=lambda x: x["date"])
    out["upcoming"].sort(key=lambda x: x["date"])
    out["sol"] = sol(snap, today)
    return out


def urgent(dl: dict) -> list[str]:
    """Reasons for a Slack ping (counts and days only: no names, amounts or medical details)."""
    why = []
    late = dl["overdue"] + dl["long_overdue"]
    if late:
        oldest = max(-i["days"] for i in late)
        why.append(f"{len(late)} overdue task{'s' if len(late) != 1 else ''} (oldest {oldest} day{'s' if oldest != 1 else ''} late)")
    if dl["due_soon"]:
        n = len(dl["due_soon"])
        why.append(f"{n} item{'s' if n != 1 else ''} due today or within {settings.digest_urgent_days} day"
                   f"{'s' if settings.digest_urgent_days != 1 else ''}")
    s = dl.get("sol")
    if s and s["urgent"]:
        why.append(f"Statute of limitations {'passed ' + str(-s['days']) + ' days ago' if s['days'] < 0 else 'in ' + str(s['days']) + ' days'}"
                   f" ({s['nice']})")
    return why


__all__ = ["lists", "urgent", "contact_for", "phone", "what", "sol", "nice_date"]
