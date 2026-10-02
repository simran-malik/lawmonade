"""The money numbers at the top of the brief. Done by code, never by the AI.

Each result says where it came from and how sure we are:
  sure = ("exact", ...)  copied from a Clio field
         ("calc", ...)   added up by code from Clio items
         ("check", ...)  read out of free text: a person should check it (with a short reason)
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


def kpis(snap: dict) -> list[dict]:
    out = []
    W = "Clio" if snap.get("source") == "clio" else "Sample file"

    # 1. Case value
    v, name = field(snap, "case_value")
    why_text, _ = field(snap, "value_why")
    value = to_number(v)
    out.append(dict(label="Case value (firm estimate)", value=usd(value), sub=first_line(why_text),
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
    out.append(dict(label="Coverage (first limit listed)", value=usd(first), sub=sub,
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
    out.append(dict(label="Lien (first listed)", value=usd(la[0]) if la else "—", sub=first_line(lien_text),
                    source=f"{W} field “{lname}”" if lname else "No lien field found",
                    sure=("check", "Check"), why=lwhy, warn=not la))

    # 4. Medical bills
    sp, sname = field(snap, "specials")
    spv = to_number(sp)
    out.append(dict(label="Medical bills to date", value=usd(spv), sub="May be negotiated down at the end.",
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
    out.append(dict(label="Firm has spent", value=usd(spent), sub=sub,
                    source=f"Added up from {len(ex)} {W} expenses",
                    sure=("calc", "Calculated") if not missing else ("check", "Check"),
                    why=f"{len(missing)} expenses have no amount." if missing else "", warn=bool(missing),
                    items=[e["src"]["label"] + f" · {usd(e.get('amount'))} · {first_line(e.get('title'))}" for e in firm]))
    return out
