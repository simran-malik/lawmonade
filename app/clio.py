"""Read a case live from Clio Manage. READ-ONLY: only GET requests, ever.

load_steps(query) -> (state, [(step label, function), ...])
    The screen runs the steps one by one so it can show progress.
    When all have run, state["snapshot"] holds the case in our shape (see app/snapshot.py).
"""
import json
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote

import requests

from app import retry
from app.config import settings
from app.log import get, stage
from app.snapshot import nice_date, now_iso, src

W = "Clio"
LOG = get("clio")


class ClioError(Exception):
    """A problem with a plain-words message and what to do next."""

    def __init__(self, message: str, fix: str):
        super().__init__(message)
        self.message, self.fix = message, fix


class ClioChoice(ClioError):
    """More than one case matches the search. `choices` lists them so a person picks the right one."""

    def __init__(self, query: str, choices: list[dict]):
        super().__init__(f"{len(choices)} cases in Clio match \"{query}\".", "Pick the right one below.")
        self.choices = choices


def _choice(m: dict) -> dict:
    return {"id": m["id"], "number": m.get("display_number", ""), "client": _name(m.get("client")),
            "description": m.get("description", ""), "status": m.get("status", "")}


def _headers():
    if not settings.clio_access_token:
        raise ClioError("Law-monade isn't connected to Clio yet.",
                        "Add your Clio access token to the .env file (see SETUP.md), then try again.")
    return {"Authorization": f"Bearer {settings.clio_access_token}"}


def _get(url: str, params: dict | None = None) -> requests.Response:
    """One GET to Clio. Retries timeouts, 429 and 5xx (GETs are safe to repeat); plain-words errors otherwise."""
    def once() -> requests.Response:
        r = requests.get(url, params=params, headers=_headers(), timeout=30)
        t = retry.from_status(r.status_code, r.headers)
        if t:
            raise t
        return r

    try:
        r = retry.run(once, safe_to_repeat=True, what="clio GET", to_transient=retry.from_requests_error)
    except retry.Transient as t:
        if t.status == 429:
            raise ClioError("Clio asked us to slow down.", "Wait a minute, then try again.") from None
        raise ClioError("Clio isn't responding properly right now.",
                        "Try again in a minute. You can also open the last saved copy or the sample case.") from None
    except requests.RequestException:
        raise ClioError("We couldn't reach Clio.",
                        "Check your internet connection, then try again. You can also try the sample case.") from None
    if r.status_code == 401:
        raise ClioError("Your Clio sign-in has expired.",
                        "Get a new access token (REQUIREMENTS.md, section 8, steps 5-6) and put it in .env.")
    if r.status_code == 403:
        raise ClioError("Law-monade isn't allowed to read part of this case.",
                        "In the Clio developer portal, give the app Read access to everything listed in SETUP.md.")
    return r


def _get_all(path: str, params: dict, field_options: list[str]) -> list[dict]:
    """All pages. Tries richer field lists first; if Clio rejects one (400), tries the next."""
    url = f"{settings.clio_base}/api/v4/{path}"
    for fields in field_options:
        r = _get(url, {**params, "fields": fields, "limit": 200})
        if r.status_code == 400:
            continue
        r.raise_for_status()
        rows, data = [], r.json()
        rows += data.get("data", [])
        nxt = data.get("meta", {}).get("paging", {}).get("next")
        while nxt:
            data = _get(nxt).json()
            rows += data.get("data", [])
            nxt = data.get("meta", {}).get("paging", {}).get("next")
        return rows
    raise ClioError(f"Clio didn't accept our request for {path}.", "This is a bug on our side. Try the sample case for now.")


# ---------- links into Clio's own web app ----------
# Checked by hand in Clio Manage (Oct 2026):
#   notes / communications / tasks tabs accept ?query={"value": "..."} and fill their search box
#   documents/<id>/details opens that document
#   tasks?taskId=<id> and notes?id=<id> open the item in EDIT mode, so we don't use them
#   tasks, calendar and activities: we link the tab and show what to type in its search box
def _search(text: str) -> str:
    words = " ".join(str(text or "").split())[:80].rsplit(" ", 1)[0] if len(str(text or "")) > 80 else " ".join(str(text or "").split())
    return quote(json.dumps({"value": words}, separators=(",", ":")), safe=":,")


def item_link(kind: str, matter_id, item_id, title: str) -> tuple[str, str]:
    """(url, hint). hint = what to type in Clio's search box when the address can't do it."""
    base = f"{settings.clio_base}/nc/#/matters/{matter_id}"
    if kind == "Note":
        return f"{base}/notes?query={_search(title)}", ""
    if kind in ("Email", "Phone call"):
        return f"{base}/communications?query={_search(title)}", ""
    if kind == "Task":      # tasks?taskId= opens the task in EDIT mode, so link the tab + a search hint instead
        return f"{base}/tasks", title
    if kind == "Document":
        return f"{settings.clio_base}/nc/#/documents/{item_id}/details", ""
    if kind == "Calendar":
        return f"{base}/calendar", title
    if kind == "Expense":
        return f"{base}/activities", title
    return base, ""


def _with_link(item: dict, matter_id) -> dict:
    url, hint = item_link(item["src"]["kind"], matter_id, item["id"], item.get("title", ""))
    item["src"]["url"], item["src"]["hint"] = url, hint
    return item


def contact_email(contact_id) -> str:
    """The contact's main email in Clio, or "" if it has none."""
    if not contact_id:
        return ""
    url = f"{settings.clio_base}/api/v4/contacts/{contact_id}.json"
    for fields in ("id,primary_email_address", "id,email_addresses{address,primary}"):
        r = _get(url, {"fields": fields})
        if r.status_code == 400:
            continue
        if not r.ok:
            return ""
        d = r.json().get("data", {})
        if d.get("primary_email_address"):
            return d["primary_email_address"]
        em = d.get("email_addresses") or []
        return next((e["address"] for e in em if e.get("primary")), em[0]["address"] if em else "")
    return ""


def _assignee_reach(assignees: list) -> dict:
    """{(type, id): {email, phone}} for the people tasks are assigned to.
    Users (firm staff): one users.json call (email; phone if the account exposes it).
    Contacts: one GET per contact. Never fails the load: no permission or a rejected field just means no details."""
    out = {}
    if not any(assignees):
        return out
    try:
        for u in _get_all("users.json", {}, ["id,name,email,phone_number", "id,name,email"]):
            out[("User", u.get("id"))] = {"email": u.get("email") or "", "phone": u.get("phone_number") or ""}
    except (ClioError, requests.RequestException) as e:
        LOG.info("[clio.users] firm users not readable (%s); task assignees shown by name only", getattr(e, "message", e))
    ids = {a.get("id") for a in assignees if a and a.get("type") == "Contact" and a.get("id")}

    def contact(cid):
        try:
            d = _get(f"{settings.clio_base}/api/v4/contacts/{cid}.json",
                     {"fields": "id,primary_email_address,primary_phone_number"})
            d = d.json().get("data", {}) if d.status_code == 200 else {}
        except (ClioError, requests.RequestException, ValueError):
            d = {}
        return cid, {"email": d.get("primary_email_address") or "", "phone": d.get("primary_phone_number") or ""}

    with ThreadPoolExecutor(max_workers=4) as pool:
        for cid, r in pool.map(contact, ids):
            out[("Contact", cid)] = r
    return out


def _name(x) -> str:
    return (x or {}).get("name", "") if isinstance(x, dict) else ""


def load_steps(query: str, matter_id=None):
    st = {}
    base = settings.clio_base

    def find():
        rows = _get_all("matters.json", {"query": query},
                        ["id,display_number,description,status,open_date,statute_of_limitations,"
                         "matter_stage{name},practice_area{name},client{id,name,primary_phone_number,primary_email_address},"
                         "responsible_attorney{id,name,email}",
                         "id,display_number,description,status,open_date,statute_of_limitations,"
                         "matter_stage{name},practice_area{name},client{id,name}",
                         "id,display_number,description,status,open_date,statute_of_limitations"])
        if matter_id is not None:                      # a person already picked one of several matches
            rows = [r for r in rows if str(r["id"]) == str(matter_id)]
        if not rows:
            raise ClioError(f"No case in Clio matches \"{query}\".", "Check the spelling, or search by client last name.")
        if len(rows) > 1:                              # never guess: opening the wrong client's case is the worst bug
            raise ClioChoice(query, [_choice(r) for r in rows])
        m = rows[0]
        cf = _get(f"{base}/api/v4/matters/{m['id']}.json",
                  {"fields": "id,custom_field_values{id,value,field_name}"}).json().get("data", {})
        st["matter"] = {
            "id": m["id"], "number": m.get("display_number", ""), "description": m.get("description", ""),
            "status": m.get("status", ""), "stage": _name(m.get("matter_stage")).title(),
            "practice_area": _name(m.get("practice_area")), "open_date": m.get("open_date"),
            "sol_date": m.get("statute_of_limitations"), "client": _name(m.get("client")),
            "url": f"{base}/nc/#/matters/{m['id']}",
            # for the daily digest: who gets it, and the client's phone for "text the client"
            "client_phone": (m.get("client") or {}).get("primary_phone_number") or "",
            "client_email": (m.get("client") or {}).get("primary_email_address") or "",
            "attorney": {"name": _name(m.get("responsible_attorney")),
                         "email": (m.get("responsible_attorney") or {}).get("email") or ""},
        }
        st["fields"] = {c.get("field_name", ""): c.get("value") for c in cf.get("custom_field_values", [])}

    def notes_and_emails():
        mid = st["matter"]["id"]
        st["notes"] = [{"id": n["id"], "date": n.get("date") or n.get("created_at"), "title": n.get("subject", ""),
                        "text": n.get("detail", ""),
                        "src": src(W, "Note", n["id"], f"Note · {nice_date(n.get('date') or n.get('created_at'))} · {n.get('subject', '')}")}
                       for n in _get_all("notes.json", {"type": "Matter", "matter_id": mid},
                                         ["id,subject,detail,date,created_at", "id,subject,detail,created_at"])]
        comms = []
        for c in _get_all("communications.json", {"matter_id": mid},
                          ["id,type,subject,body,date,received_at", "id,type,subject,body,date"]):
            kind = "Email" if "Email" in (c.get("type") or "") else "Phone call"
            comms.append({"id": c["id"], "date": c.get("date") or c.get("received_at"), "kind": kind,
                          "title": c.get("subject", ""), "text": c.get("body", ""),
                          "src": src(W, kind, c["id"], f"{kind} · {nice_date(c.get('date'))} · {c.get('subject', '')}")})
        st["communications"] = comms

    def tasks_calendar_money():
        mid = st["matter"]["id"]
        rows = _get_all("tasks.json", {"matter_id": mid},
                        ["id,name,description,due_at,status,completed_at,assignee{id,name,type}",
                         "id,name,description,due_at,status,completed_at,assignee{id,name}",
                         "id,name,description,due_at,status,completed_at", "id,name,description,due_at,status"])
        reach = _assignee_reach([t.get("assignee") for t in rows])
        st["tasks"] = []
        for t in rows:
            a = t.get("assignee") or {}
            r = reach.get((a.get("type") or "User", a.get("id")), {})
            st["tasks"].append({
                "id": t["id"], "date": t.get("due_at"), "title": t.get("name", ""), "text": t.get("description", ""),
                "status": t.get("status", ""), "assignee": _name(a),
                # the task's responsible person: Clio "assignee" is a firm User or a Contact
                "assignee_type": a.get("type") or ("User" if a else ""),
                "assignee_email": r.get("email", ""), "assignee_phone": r.get("phone", ""),
                "src": src(W, "Task", t["id"], f"Task · due {nice_date(t.get('due_at'))} · {t.get('name', '')}")})
        st["calendar"] = [{"id": e["id"], "date": e.get("start_at"), "end": e.get("end_at"), "title": e.get("summary", ""), "text": e.get("description", ""),
                           "src": src(W, "Calendar", e["id"], f"Calendar · {nice_date(e.get('start_at'))} · {e.get('summary', '')}")}
                          for e in _get_all("calendar_entries.json", {"matter_id": mid},
                                            ["id,summary,description,start_at,end_at", "id,summary,start_at"])]
        ex = []
        for a in _get_all("activities.json", {"matter_id": mid, "type": "ExpenseEntry"},
                          ["id,date,price,quantity,total,note,expense_category{name}", "id,date,price,quantity,total,note"]):
            amt = a.get("total")
            if amt is None and a.get("price") is not None:
                amt = a["price"] * (a.get("quantity") or 1)
            ex.append({"id": a["id"], "date": a.get("date"), "amount": amt, "category": _name(a.get("expense_category")),
                       "title": (a.get("note") or "").split("\n")[0], "text": a.get("note", ""),
                       "src": src(W, "Expense", a["id"], f"Expense · {nice_date(a.get('date'))}")})
        st["expenses"] = ex

    def docs_and_people():
        mid = st["matter"]["id"]
        st["documents"] = [{"id": d["id"], "date": d.get("received_at") or d.get("created_at"), "title": d.get("name", ""),
                            "folder": _name(d.get("parent")), "text": "",
                            "src": src(W, "Document", d["id"], f"Document · {d.get('name', '')}")}
                           for d in _get_all("documents.json", {"matter_id": mid},
                                             ["id,name,received_at,created_at,parent{name}", "id,name,created_at"])]
        # Ask for the email in the same request (1 call instead of 1 per contact); if Clio rejects that
        # field list, fall back and fetch the missing emails a few at a time.
        rels = _get_all("relationships.json", {"matter_id": mid},
                        ["id,description,contact{id,name,primary_email_address,primary_phone_number}",
                         "id,description,contact{id,name,primary_email_address}", "id,description,contact{id,name}",
                         "id,description"])
        missing = [(r.get("contact") or {}).get("id") for r in rels
                   if (r.get("contact") or {}).get("id") and "primary_email_address" not in (r.get("contact") or {})]
        with ThreadPoolExecutor(max_workers=4) as pool:
            extra = dict(zip(missing, pool.map(contact_email, missing)))
        people = []
        for r in rels:
            c = r.get("contact") or {}
            people.append({"id": r["id"], "contact_id": c.get("id"), "name": _name(c), "role": r.get("description", ""),
                           "email": c.get("primary_email_address") or extra.get(c.get("id"), ""),
                           "phone": c.get("primary_phone_number") or ""})
        st["contacts"] = people

    def assemble():
        mid = st["matter"]["id"]
        for k in ("notes", "communications", "tasks", "calendar", "expenses", "documents"):
            st[k] = [_with_link(it, mid) for it in st.get(k, [])]
        st["snapshot"] = {"source": "clio", "fetched_at": now_iso(),
                          **{k: st.get(k, []) for k in ("notes", "communications", "tasks", "calendar",
                                                        "expenses", "documents", "contacts")},
                          "matter": st["matter"], "fields": st["fields"]}

    def timed(name: str, fn, counted: tuple[str, ...] = ()):
        """Log one line per step: "[clio.notes] 1.1s, notes=42, communications=69"."""
        def run():
            with stage(f"clio.{name}", LOG) as info:
                fn()
                info.update({k: len(st.get(k) or []) for k in counted})
        return run

    return st, [
        ("Finding the case in Clio", timed("find", find)),
        ("Reading notes and emails", timed("notes", notes_and_emails, ("notes", "communications"))),
        ("Reading tasks, calendar and expenses", timed("tasks", tasks_calendar_money, ("tasks", "calendar", "expenses"))),
        ("Reading documents and contacts", timed("documents", docs_and_people, ("documents", "contacts"))),
        ("Putting it together", timed("assemble", assemble)),
    ]
