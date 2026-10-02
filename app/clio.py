"""Read a case live from Clio Manage. READ-ONLY: only GET requests, ever.

load_steps(query) -> (state, [(step label, function), ...])
    The screen runs the steps one by one so it can show progress.
    When all have run, state["snapshot"] holds the case in our shape (see app/snapshot.py).
"""
import requests

from app.config import settings
from app.snapshot import nice_date, now_iso, src

W = "Clio"


class ClioError(Exception):
    """A problem with a plain-words message and what to do next."""

    def __init__(self, message: str, fix: str):
        super().__init__(message)
        self.message, self.fix = message, fix


def _headers():
    if not settings.clio_access_token:
        raise ClioError("Law-monade isn't connected to Clio yet.",
                        "Add your Clio access token to the .env file (see SETUP.md), then try again.")
    return {"Authorization": f"Bearer {settings.clio_access_token}"}


def _get(url: str, params: dict | None = None) -> requests.Response:
    try:
        r = requests.get(url, params=params, headers=_headers(), timeout=30)
    except requests.RequestException:
        raise ClioError("We couldn't reach Clio.",
                        "Check your internet connection, then try again. You can also try the sample case.") from None
    if r.status_code == 401:
        raise ClioError("Your Clio sign-in has expired.",
                        "Get a new access token (REQUIREMENTS.md, section 8, steps 5-6) and put it in .env.")
    if r.status_code == 403:
        raise ClioError("Law-monade isn't allowed to read part of this case.",
                        "In the Clio developer portal, give the app Read access to everything listed in SETUP.md.")
    if r.status_code == 429:
        raise ClioError("Clio asked us to slow down.", "Wait a minute, then try again.")
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


def _name(x) -> str:
    return (x or {}).get("name", "") if isinstance(x, dict) else ""


def load_steps(query: str):
    st = {}
    base = settings.clio_base

    def find():
        rows = _get_all("matters.json", {"query": query},
                        ["id,display_number,description,status,open_date,statute_of_limitations,"
                         "matter_stage{name},practice_area{name},client{id,name}",
                         "id,display_number,description,status,open_date,statute_of_limitations"])
        if not rows:
            raise ClioError(f"No case in Clio matches \"{query}\".", "Check the spelling, or search by client last name.")
        m = rows[0]
        cf = _get(f"{base}/api/v4/matters/{m['id']}.json",
                  {"fields": "id,custom_field_values{id,value,field_name}"}).json().get("data", {})
        st["matter"] = {
            "id": m["id"], "number": m.get("display_number", ""), "description": m.get("description", ""),
            "status": m.get("status", ""), "stage": _name(m.get("matter_stage")).title(),
            "practice_area": _name(m.get("practice_area")), "open_date": m.get("open_date"),
            "sol_date": m.get("statute_of_limitations"), "client": _name(m.get("client")),
            "url": f"{base}/nc/#/matters/{m['id']}",
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
        st["tasks"] = [{"id": t["id"], "date": t.get("due_at"), "title": t.get("name", ""), "text": t.get("description", ""),
                        "status": t.get("status", ""),
                        "src": src(W, "Task", t["id"], f"Task · due {nice_date(t.get('due_at'))} · {t.get('name', '')}")}
                       for t in _get_all("tasks.json", {"matter_id": mid},
                                         ["id,name,description,due_at,status,completed_at", "id,name,description,due_at,status"])]
        st["calendar"] = [{"id": e["id"], "date": e.get("start_at"), "title": e.get("summary", ""), "text": e.get("description", ""),
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
        people = []
        for r in _get_all("relationships.json", {"matter_id": mid}, ["id,description,contact{id,name}", "id,description"]):
            c = r.get("contact") or {}
            people.append({"id": r["id"], "contact_id": c.get("id"), "name": _name(c),
                           "role": r.get("description", ""), "email": contact_email(c.get("id"))})
        st["contacts"] = people

    def assemble():
        st["snapshot"] = {"source": "clio", "fetched_at": now_iso(),
                          **{k: st.get(k, []) for k in ("notes", "communications", "tasks", "calendar",
                                                        "expenses", "documents", "contacts")},
                          "matter": st["matter"], "fields": st["fields"]}

    return st, [
        ("Finding the case in Clio", find),
        ("Reading notes and emails", notes_and_emails),
        ("Reading tasks, calendar and expenses", tasks_calendar_money),
        ("Reading documents and contacts", docs_and_people),
        ("Putting it together", assemble),
    ]
