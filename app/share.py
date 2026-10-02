"""What a medical provider may see. Built by code from the case snapshot; the attorney reviews and edits
it before a link is made. Only the approved, frozen copy is stored and shown to the provider.

Never shared: notes, emails, calls, case value, coverage reasoning, strategy. Only these sections exist.
"""
import re
from datetime import date, datetime

from app.kpis import first_line, is_medical
from app.snapshot import nice_date

PROVIDER_ROLE = re.compile(r"provider|hospital|medical|clinic|chiropract|therap|surg|ortho|radiolog|imaging|"
                           r"neurolog|physiatr|rehab|emg|doctor|physician|treating", re.I)
# Words that appear in many provider names, so they can't tell providers apart
GENERIC = set("""inc llc pllc p.c pc ltd the and of new york offices office services service center centre group
associates medical medicine health care clinic hospital surgical surgery orthopaedic orthopedic chiropractic physical
therapy rehabilitation radiology imaging diagnostic neurology interventional advanced provider dr md m.d d.c""".split())
CLOSED_STAGES = re.compile(r"closed|disburs|settled", re.I)

SECTIONS = {
    "status": "Case status",
    "needs": "What we need from their office",
    "bills": "Their bills: expected payment range",
    "records": "Records we have from them",
    "coverage": "Insurance coverage behind the case",
}
DEFAULT_ON = ["status", "needs", "bills", "records"]


def providers(snap: dict, show_all: bool = False) -> list[dict]:
    return [c for c in snap.get("contacts", []) if show_all or PROVIDER_ROLE.search(c.get("role", ""))]


def name_keys(name: str) -> list[str]:
    """Distinctive words of a provider name, e.g. 'McCulloch Orthopaedic Surgical Services' -> ['mcculloch']."""
    toks = [t.strip(".'-") for t in re.findall(r"[a-z][a-z.'-]+", name.lower())]
    toks = [t for t in toks if len(t) >= 4 and t not in GENERIC]
    if len(toks) == 2 and len(name.split()) == 2:     # a person "First Last": the last name is distinctive
        toks = toks[1:]
    return toks


def mentions(item: dict, keys: list[str]) -> bool:
    text = f"{item.get('title', '')} {item.get('text', '')}".lower()
    return any(k in text for k in keys)


def doc_name(title: str) -> str:
    """'05-medical-bills__created__sportscare-itemized-bill-2023-12-14.pdf' -> 'Sportscare itemized bill 2023 12 14'."""
    t = re.sub(r"\.pdf$", "", title, flags=re.I).split("__")[-1].replace("-", " ").replace("_", " ")
    return t[:1].upper() + t[1:]


def is_open(task: dict) -> bool:
    return (task.get("status") or "").lower() not in ("complete", "completed", "done")


def build(snap: dict, provider: dict) -> dict:
    """Everything this provider COULD see, with the items each section is based on (the attorney trims it)."""
    keys = name_keys(provider["name"])
    m = snap["matter"]
    active = (m.get("status", "").lower() == "open") and not CLOSED_STAGES.search(m.get("stage", ""))
    needs = [t for t in snap.get("tasks", []) if is_open(t) and mentions(t, keys)]
    bills = [e for e in snap.get("expenses", []) if is_medical(e) and mentions(e, keys)]
    records = [d for d in snap.get("documents", []) if mentions(d, keys)]
    billed = sum(e["amount"] for e in bills if e.get("amount") is not None)
    from app.kpis import field
    cov_text, cov_field = field(snap, "coverage")
    return {
        "provider": provider, "keys": keys,
        "status": {"active": active, "stage": m.get("stage", ""), "status": m.get("status", ""),
                   "client": m.get("client", ""), "updated": snap.get("fetched_at")},
        "needs": needs, "bills": bills, "billed": billed if bills else None,
        "records": records, "coverage": first_line(cov_text), "coverage_field": cov_field,
    }


def default_message(provider_name: str, client: str, firm: str) -> str:
    return (f"Hello {provider_name},\n\n"
            f"Here is an update on our client {client or 'your patient'}'s case: where it stands and what we need "
            f"from your office right now.\n\n"
            f"Thank you for your care of our client. Please reply to this email with any questions.\n\n{firm}")


def payload(draft: dict, chosen: list[str], need_ids: list[str], record_ids: list[str],
            billed: float | None, reduction: tuple[int, int], message: str, firm: str) -> dict:
    """The frozen copy the provider will see. Only chosen sections, only ticked items."""
    p = {"provider": draft["provider"]["name"], "client": draft["status"]["client"], "firm": firm,
         "message": message.strip(), "made": datetime.now().isoformat(timespec="minutes"), "sections": chosen}
    if "status" in chosen:
        p["status"] = {k: draft["status"][k] for k in ("active", "stage", "status", "updated")}
    if "needs" in chosen:
        p["needs"] = [{"what": first_line(t["title"]).split(" - ", 1)[-1], "detail": t.get("text", ""),
                       "due": t.get("date")} for t in draft["needs"] if str(t["id"]) in need_ids]
    if "bills" in chosen:
        lo_r, hi_r = reduction
        p["bills"] = {"billed": billed,
                      "low": None if billed is None else billed * (1 - hi_r / 100),
                      "high": None if billed is None else billed * (1 - lo_r / 100)}
    if "records" in chosen:
        p["records"] = [{"name": doc_name(d["title"]), "date": d.get("date")} for d in draft["records"]
                        if str(d["id"]) in record_ids]
    if "coverage" in chosen:
        p["coverage"] = draft["coverage"]
    return p


def overdue(due) -> bool:
    try:
        return datetime.fromisoformat(str(due).replace("Z", "+00:00")).date() < date.today()
    except (TypeError, ValueError):
        return False


__all__ = ["SECTIONS", "DEFAULT_ON", "providers", "build", "payload", "name_keys", "doc_name", "overdue", "nice_date"]
