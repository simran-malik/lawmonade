"""One shape for a case, whether it comes live from Clio or from the sample file.
The screens only read this shape, so they never care where the data came from.

snapshot = {
  "source": "clio" | "sample",  "fetched_at": ISO time,
  "matter":  {id, number, description, status, stage, practice_area, open_date, sol_date, client, url,
              client_phone, client_email, attorney: {name, email}},   (newer snapshots; older ones may lack these)
  "fields":  {custom field name: value},
  "contacts": [{id, name, role, email, phone}],
  "notes" | "communications" | "tasks" | "calendar" | "expenses" | "documents": [item, ...]
}
Every item has "src": {"where": "Clio" | "Sample file", "kind": "Note", "id": ..., "label": "Note · May 7, 2023 · Intake summary"}
so the screen can always show where a fact came from.
"""
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from app.config import settings

LISTS = ("notes", "communications", "tasks", "calendar", "expenses", "documents")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def nice_date(value) -> str:
    """'2023-05-07' or '2023-05-07T10:00:00Z' -> 'May 7, 2023'. Empty stays empty."""
    if not value:
        return ""
    try:
        d = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return d.strftime("%b %-d, %Y")
    except ValueError:
        return str(value)


def src(where: str, kind: str, id_, label: str) -> dict:
    return {"where": where, "kind": kind, "id": str(id_), "label": label}


# ---------- save / load (JSON files, written safely) ----------
def _path(matter_id) -> Path:
    return settings.snapshot_dir / str(matter_id) / "snapshot.json"


def _write(p: Path, snap: dict) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=p.parent, suffix=".tmp")
    with os.fdopen(fd, "w") as f:
        json.dump(snap, f, indent=1)
    os.replace(tmp, p)          # rename = never a half-written file


def _stamp(fetched_at: str) -> str:
    return re.sub(r"[^0-9T]", "", str(fetched_at or now_iso()))[:15]     # '20261002T170000'


def save(snap: dict) -> Path:
    """Save the latest copy (snapshot.json) AND a dated copy in snapshots/, keeping SNAPSHOT_KEEP of them.
    The dated copies answer "what changed since I last looked" and "what did the attorney see when they approved"."""
    p = _path(snap["matter"]["id"])
    _write(p.parent / "snapshots" / f"{_stamp(snap.get('fetched_at'))}.json", snap)
    _write(p, snap)
    for old in versions(snap["matter"]["id"])[:-settings.snapshot_keep or None]:
        old.unlink(missing_ok=True)
    return p


def versions(matter_id) -> list[Path]:
    """Dated copies of one case, oldest first."""
    return sorted((settings.snapshot_dir / str(matter_id) / "snapshots").glob("*.json"))


def load_version(matter_id, fetched_at: str) -> dict | None:
    """The copy of the case as it was at `fetched_at` (e.g. the one an approval was made on)."""
    p = settings.snapshot_dir / str(matter_id) / "snapshots" / f"{_stamp(fetched_at)}.json"
    return json.loads(p.read_text()) if p.exists() else None


def purge(matter_id) -> int:
    """Retention: delete every saved copy of one case. Returns how many files were removed."""
    import shutil
    d = settings.snapshot_dir / str(matter_id)
    n = sum(1 for _ in d.rglob("*.json")) if d.exists() else 0
    shutil.rmtree(d, ignore_errors=True)
    return n


def load_saved(matter_id) -> dict | None:
    p = _path(matter_id)
    return json.loads(p.read_text()) if p.exists() else None


def find_saved(query: str) -> dict | None:
    """Newest snapshot saved from live Clio whose client, description or number matches `query`.
    Used when Clio can't be reached, so the team still sees the case (with its "as of" time)."""
    q = (query or "").strip().lower()
    best = None
    for p in settings.snapshot_dir.glob("*/snapshot.json"):
        try:
            snap = json.loads(p.read_text())
        except (OSError, ValueError):
            continue
        m = snap.get("matter") or {}
        text = " ".join(str(m.get(k) or "") for k in ("client", "description", "number")).lower()
        if snap.get("source") == "clio" and q and q in text:
            if best is None or snap.get("fetched_at", "") > best.get("fetched_at", ""):
                best = snap
    return best


def counts(snap: dict) -> dict:
    return {k: len(snap.get(k, [])) for k in LISTS} | {"contacts": len(snap.get("contacts", []))}


# ---------- sample file (Demo mode) ----------
_PH = re.compile(r"^\{\{(\w+)(?::(.+))?\}\}$")


def _ph(value) -> tuple[str, str]:
    """'{{stage:Litigation}}' -> ('stage', 'Litigation')."""
    m = _PH.match(str(value or ""))
    return (m.group(1), m.group(2) or "") if m else ("", str(value or ""))


def from_sample_file(path: str | Path) -> dict:
    """Read the organizers' Clio request file (sapini-clio-data.json) into our shape."""
    d = json.loads(Path(path).read_text())
    W = "Sample file"
    m = d["matter"]["body"]
    names, emails, phones = {}, {}, {}
    for c in d["contacts"]["items"]:
        b = c["body"]
        names[c["ref"]] = (b.get("name") or " ".join(x for x in (b.get("first_name"), b.get("last_name")) if x))
        em = b.get("email_addresses") or []
        emails[c["ref"]] = next((e["address"] for e in em if e.get("default_email")), em[0]["address"] if em else "")
        ph = b.get("phone_numbers") or []
        phones[c["ref"]] = next((p.get("number", "") for p in ph if p.get("default_number")),
                                ph[0].get("number", "") if ph else "")
    client_ref = _ph(m.get("client", {}).get("id"))[1]

    snap = {
        "source": "sample", "fetched_at": now_iso(),
        "matter": {
            "id": "sample", "number": "SAMPLE", "description": m.get("description", ""),
            "status": m.get("status", ""), "stage": _ph(m.get("matter_stage", {}).get("id"))[1],
            "practice_area": "Personal Injury", "open_date": m.get("open_date"),
            "sol_date": m.get("statute_of_limitations"), "client": names.get(client_ref, ""), "url": "",
            "client_phone": phones.get(client_ref, ""), "client_email": emails.get(client_ref, ""),
            "attorney": {"name": "", "email": ""},
        },
        "fields": {_ph(v["custom_field"]["id"])[1]: v.get("value") for v in m.get("custom_field_values", [])},
        "contacts": [], "notes": [], "communications": [], "tasks": [], "calendar": [], "expenses": [], "documents": [],
    }
    for i, r in enumerate(d["relationships"]["items"], 1):
        b = r["body"]
        ref = _ph(b["contact"]["id"])[1]
        snap["contacts"].append({"id": f"R{i}", "name": names.get(ref, ""), "role": b.get("description", ""),
                                 "email": emails.get(ref, ""), "phone": phones.get(ref, "")})
    for i, it in enumerate(d["notes"]["items"], 1):
        b = it["body"]
        snap["notes"].append({"id": f"N{i}", "date": b.get("date"), "title": b.get("subject", ""),
                              "text": b.get("detail", ""),
                              "src": src(W, "Note", f"N{i}", f"Note · {nice_date(b.get('date'))} · {b.get('subject', '')}")})
    for i, it in enumerate(d["communications"]["items"], 1):
        b = it["body"]
        kind = "Email" if "Email" in b.get("type", "") else "Phone call"
        snap["communications"].append({"id": f"C{i}", "date": b.get("date"), "kind": kind,
                                       "title": b.get("subject", ""), "text": b.get("body", ""),
                                       "src": src(W, kind, f"C{i}", f"{kind} · {nice_date(b.get('date'))} · {b.get('subject', '')}")})
    for i, it in enumerate(d["tasks"]["items"], 1):
        b = it["body"]
        snap["tasks"].append({"id": f"T{i}", "date": b.get("due_at"), "title": b.get("name", ""),
                              "text": b.get("description", ""), "status": b.get("status", ""),
                              "src": src(W, "Task", f"T{i}", f"Task · due {nice_date(b.get('due_at'))} · {b.get('name', '')}")})
    for i, it in enumerate(d["calendar_entries"]["items"], 1):
        b = it["body"]
        snap["calendar"].append({"id": f"E{i}", "date": b.get("start_at"), "end": b.get("end_at"), "title": b.get("summary", ""),
                                 "text": b.get("description", ""),
                                 "src": src(W, "Calendar", f"E{i}", f"Calendar · {nice_date(b.get('start_at'))} · {b.get('summary', '')}")})
    for i, it in enumerate(d["expenses"]["items"], 1):
        b = it["body"]
        amt = (b.get("price") or 0) * (b.get("quantity") or 1) if b.get("price") is not None else None
        snap["expenses"].append({"id": f"X{i}", "date": b.get("date"), "amount": amt, "category": "",
                                 "title": (b.get("note") or "").split("\n")[0], "text": b.get("note", ""),
                                 "src": src(W, "Expense", f"X{i}", f"Expense · {nice_date(b.get('date'))}")})
    for i, it in enumerate(d["documents"]["items"], 1):
        b = it["body"]
        snap["documents"].append({"id": f"D{i}", "date": b.get("received_at"), "title": b.get("name", ""),
                                  "folder": _ph(b.get("parent", {}).get("id"))[1], "text": "",
                                  "src": src(W, "Document", f"D{i}", f"Document · {b.get('name', '')}")})
    return snap
