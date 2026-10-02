"""The money numbers at the top of the brief. Done by code, never by the AI.

Each result says where it came from and how sure we are:
  sure = ("exact", ...)  copied from a Clio field
         ("calc", ...)   added up by code from Clio items
         ("check", ...)  read out of free text: a person should check it (with a short reason)
         ("ai", ...)     sorted by the AI, then every item checked by code against the Clio text (lien card only)
         ("edited", ...) a person corrected it in Law-monade (saved in our DB, Clio is never changed)
Each card also has: key (stable id), amount (the number), link (where to see it in Clio, or None).
Field names differ between firms, so we look for several common names (FIELD_NAMES).
"""
import re

FIELD_NAMES = {
    "case_value": ["Estimated Case Value", "Case Value", "Estimated Value", "Settlement Value"],
    "value_why": ["Case Value Rationale", "Value Rationale", "Valuation Notes"],
    "coverage": ["Policy Limits", "Coverage", "Insurance Limits", "Policy Limit"],
    "coverage_ok": ["Policy Limits Confirmed", "Limits Confirmed"],
    "liens": ["Health Insurance or Lien Holder", "Liens", "Lien Holder", "Lien Amount"],
    "specials": ["Medical Specials To Date", "Medical Specials", "Medical Bills", "Specials"],
    "incident": ["Date of Incident", "Incident Date", "Date of Loss", "Accident Date"],
}
MONEY = re.compile(r"\$\s?([\d,]+(?:\.\d{1,2})?)")
MEDICAL = re.compile(r"medical|treatment|provider|lien", re.I)


def field(snap: dict, key: str) -> tuple[object, str]:
    """(value, field name) for the first matching field that has a value."""
    fields = {k.lower(): (k, v) for k, v in snap.get("fields", {}).items()}
    for name in FIELD_NAMES[key]:
        k, v = fields.get(name.lower(), (None, None))
        if v not in (None, ""):
            return v, k
    return None, ""


def clio_link(snap: dict, field_name: str) -> dict | None:
    """The case's Custom Fields tab in Clio (checked in Clio, Oct 2026: <matter url>/custom-fields).
    No address opens one field, so we say which field to look for."""
    url = (snap.get("matter") or {}).get("url")
    if not url or not field_name:
        return None
    return {"url": f"{url}/custom-fields", "place": "the Custom Fields tab", "hint": f"“{field_name}”"}


def amounts(text) -> list[float]:
    return [float(x.replace(",", "")) for x in MONEY.findall(str(text or ""))]


def to_number(v) -> float | None:
    if isinstance(v, (int, float)):
        return float(v)
    a = amounts(v) or [float(x) for x in re.findall(r"^\s*([\d.]+)\s*$", str(v or ""))]
    return a[0] if a else None


def usd(x: float | None) -> str:
    return "—" if x is None else f"${x:,.0f}"


def first_line(text) -> str:
    """First line of a text, in full (never cut off with "…")."""
    return str(text or "").strip().split("\n")[0]


def is_medical(e: dict) -> bool:
    """Provider bills (paid from the settlement) vs. the firm's own case costs."""
    if e.get("category"):
        return bool(MEDICAL.search(e["category"]))
    return bool(MEDICAL.search(e.get("title", ""))) and "not patient treatment" not in e.get("text", "").lower()


def lien_card(snap: dict, a: dict, lname: str, W: str) -> dict:
    """Lien card from the AI breakdown (app/liens.py). Only checked liens are added up; the rest are listed."""
    link = clio_link(snap, lname)
    liens = [i for i in a["items"] if i["kind"] == "lien" and i["checked"] and i["amount"] is not None]
    others = [i for i in a["items"] if i["kind"] != "lien" and i["checked"]]
    unchecked = a.get("unchecked", [])
    sub = " · ".join(f"{i['holder']} {usd(i['amount'])}" for i in liens) or "No lien amount in this field"
    if others:
        sub += ". Not counted: " + ", ".join(
            f"{i['holder']}" + (f" {usd(i['amount'])}" if i["amount"] is not None else "") + f" ({i['status']})"
            for i in others)
    norep = [i for i in liens if not i["repeats"]]
    n_rep = len({r["label"] for i in liens for r in i["repeats"]})
    if unchecked:
        sure, warn = ("check", "Check"), True
        why = (f"Left out {len(unchecked)} item(s) the AI read that don't match the Clio text: "
               + ", ".join(i["holder"] for i in unchecked) + ".")
    elif not liens:
        sure, warn, why = ("check", "Check"), True, "The AI found no lien amount in this field."
    elif norep:
        sure, warn = ("check", "Check"), False
        why = "Only stated in this field; no note or email repeats it: " + ", ".join(i["holder"] for i in norep) + "."
    else:
        sure, warn, why = ("ai", "AI-sorted · checked"), False, ""
        sub += f". Same amount in {n_rep} other Clio item{'s' if n_rep != 1 else ''}."
    items = [{"text": f"{i['kind_label']} · {i['holder']} · {usd(i['amount'])} · {i['status']} — “{i['quote']}”"
                      + ("" if i["checked"] else " ⚠ not in the Clio text, left out"),
              "url": (link or {}).get("url", "")} for i in a["items"]]
    seen = set()
    for i in liens:
        for r in i["repeats"]:
            if r["label"] not in seen:
                seen.add(r["label"])
                items.append({"text": f"Also says {usd(i['amount'])}: {r['label']}", "url": r.get("url", "")})
    return dict(key="lien", amount=a["total"], link=link, label="Liens asserted", value=usd(a["total"]), sub=sub,
                source=f"{W} field “{lname}” · sorted by AI, checked by code", sure=sure, why=why, warn=warn,
                items=items)


def kpis(snap: dict, liens: dict | None = None) -> list[dict]:
    """liens = app.liens.analyze(snap) result; without it (or if the AI failed) the lien card reads the first amount."""
    out = []
    W = "Clio" if snap.get("source") == "clio" else "Sample file"

    # 1. Case value
    v, name = field(snap, "case_value")
    why_text, _ = field(snap, "value_why")
    value = to_number(v)
    out.append(dict(key="case_value", amount=value, link=clio_link(snap, name),
                    label="Case value (firm estimate)", value=usd(value), sub=first_line(why_text),
                    source=f"{W} field “{name}”" if name else "No case value field found",
                    sure=("exact", "Exact") if value is not None else ("check", "Missing"),
                    why="" if value is not None else "No case value in Clio yet.", warn=value is None))

    # 2. Coverage
    cov_text, cname = field(snap, "coverage")
    ok, _ = field(snap, "coverage_ok")
    cov = amounts(cov_text)
    first = cov[0] if cov else None
    gap = (value - first) if (value is not None and first is not None) else None
    sub = first_line(cov_text) + (" · limits confirmed" if ok in (True, "true", "True", 1) else "")
    why = "Read from free text with several limits listed. Check which applies." if len(cov) > 1 else ""
    if gap and gap > 0:
        why = f"Case is worth {usd(gap)} more than this limit. " + why
    out.append(dict(key="coverage", amount=first, link=clio_link(snap, cname),
                    label="Coverage (first limit listed)", value=usd(first), sub=sub,
                    source=f"{W} field “{cname}”" if cname else "No policy limits field found",
                    sure=("check", "Check") if (len(cov) > 1 or first is None) else ("exact", "Exact"),
                    why=why.strip() or ("No policy limits in Clio yet." if first is None else ""),
                    warn=bool(gap and gap > 0) or first is None))

    # 3. Liens
    lien_text, lname = field(snap, "liens")
    la = amounts(lien_text)
    lwhy = ("No lien amount found." if not la else
            "Several amounts in this text. Showing the first; check the rest." if len(la) > 1 else
            "Amount read from free text.")
    if liens and liens.get("status") == "failed":
        lwhy += " (AI breakdown unavailable, so this is the plain reading.)"
    if liens and liens.get("status") == "ok" and liens.get("items"):
        out.append(lien_card(snap, liens, lname, W))
    else:
        out.append(dict(key="lien", amount=la[0] if la else None, link=clio_link(snap, lname),
                        label="Lien (first listed)", value=usd(la[0]) if la else "—", sub=first_line(lien_text),
                        source=f"{W} field “{lname}”" if lname else "No lien field found",
                        sure=("check", "Check"), why=lwhy, warn=not la))

    # 4. Medical bills
    sp, sname = field(snap, "specials")
    spv = to_number(sp)
    out.append(dict(key="medical_bills", amount=spv, link=clio_link(snap, sname),
                    label="Medical bills to date", value=usd(spv), sub="May be negotiated down at the end.",
                    source=f"{W} field “{sname}”" if sname else "No medical specials field found",
                    sure=("exact", "Exact") if spv is not None else ("check", "Missing"),
                    why="" if spv is not None else "No medical bills total in Clio yet.", warn=spv is None))

    # 5. Firm spend
    ex = snap.get("expenses", [])
    firm = [e for e in ex if not is_medical(e)]
    med = [e for e in ex if is_medical(e)]
    missing = [e for e in firm if e.get("amount") is None]
    spent = sum(e["amount"] for e in firm if e.get("amount") is not None)
    sub = f"{len(firm)} case costs" + (f" · {len(med)} provider bills not counted" if med else "")
    murl = (snap.get("matter") or {}).get("url")
    out.append(dict(key="firm_spend", amount=spent,
                    # Activities tab; the Expense filter can't be set from the address (checked in Clio), so we say so
                    link={"url": f"{murl}/activities", "place": "the Activities tab",
                          "hint": "“Expense” in the type filter"} if murl else None,
                    label="Firm has spent", value=usd(spent), sub=sub,
                    source=f"Added up from {len(ex)} {W} expenses",
                    sure=("calc", "Calculated") if not missing else ("check", "Check"),
                    why=f"{len(missing)} expenses have no amount." if missing else "", warn=bool(missing),
                    items=[{"text": e["src"]["label"] + f" · {usd(e.get('amount'))} · {first_line(e.get('title'))}",
                            "url": e["src"].get("url", "")} for e in firm]))
    return out


def apply_edits(cards: list[dict], edits: dict) -> list[dict]:
    """Show a person's saved correction instead of the Clio number, and keep the Clio number visible.
    edits = {card key: {"value", "note", "edited_by", "edited_at", "clio_value"}} from app.store.card_edits()."""
    for k in cards:
        e = edits.get(k["key"])
        if not e:
            continue
        k["clio_amount"], k["clio_value_text"] = k["amount"], k["value"]
        k["amount"], k["value"] = e["value"], usd(e["value"])
        k["sure"], k["warn"], k["edited"] = ("edited", "Edited"), False, e
        why = f"Corrected by {e.get('edited_by') or 'a team member'}. Clio says {k['clio_value_text']}."
        if e.get("note"):
            why += f" Reason: {e['note']}"
        if e.get("clio_value") != k["clio_amount"]:     # Clio changed after the edit: someone should look again
            why += f" Clio has changed since this edit (was {usd(e.get('clio_value'))}). Check it."
            k["warn"] = True
        k["why"] = why
    return cards
