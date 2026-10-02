"""Step 7 + 8: test the Clio connection and check the Sapini matter is complete.

READ-ONLY: this script only sends GET requests to Clio.
Run from the project folder:   python3 scripts/clio_check.py
Optional:                    python3 scripts/clio_check.py "Sapini"   (search text)
"""
import os
import sys
from pathlib import Path

import requests

BASE = "https://app.clio.com/api/v4"
ENV_FILE = Path(__file__).resolve().parent.parent / ".env"

# Expected numbers from what the Swans setup app loads (checked 2026-10-02).
# It loads more than the manual guide: +5 provider contacts, +9 "DEMO medical charges"
# expenses, +18 per-provider records/bills PDFs, and no doc-19/doc-20 big scan bundles.
EXPECTED = {
    "custom fields filled": 16,
    "related contacts (+ client)": 15,
    "notes": 42,
    "communications": 69,
    "tasks": 14,
    "calendar entries": 17,
    "expenses": 14,
    "documents": 31,
}


def load_env():
    """Read KEY=VALUE lines from this project's .env (no extra package needed)."""
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def get(path, params=None):
    """One GET call. Stops with a clear message on auth errors."""
    token = os.environ.get("CLIO_ACCESS_TOKEN", "")
    r = requests.get(
        f"{BASE}/{path}",
        params=params or {},
        headers={"Authorization": f"Bearer {token}"},
        timeout=30,
    )
    if r.status_code == 401:
        sys.exit("401 Unauthorized: CLIO_ACCESS_TOKEN is missing, wrong or expired. Redo steps 5-6.")
    if r.status_code == 403:
        sys.exit(f"403 Forbidden on {path}: your developer app is missing READ permission for this. Add it, then redo steps 5-6.")
    r.raise_for_status()
    return r.json()


def get_all(path, params):
    """GET every page (Clio returns max 200 per page)."""
    params = {**params, "limit": 200}
    rows = []
    data = get(path, params)
    rows += data.get("data", [])
    nxt = data.get("meta", {}).get("paging", {}).get("next")
    while nxt:
        r = requests.get(
            nxt,
            headers={"Authorization": f"Bearer {os.environ['CLIO_ACCESS_TOKEN']}"},
            timeout=30,
        )
        r.raise_for_status()
        data = r.json()
        rows += data.get("data", [])
        nxt = data.get("meta", {}).get("paging", {}).get("next")
    return rows


def show_details(mid):
    """List the items behind the 3 counts that can differ (read-only)."""
    print("\n===== RELATED CONTACTS (with email from Clio) =====")
    with_email = 0
    rels = get_all("relationships.json", {"matter_id": mid, "fields": "id,description,contact{id,name}"})
    for r in rels:
        c = r.get("contact") or {}
        email = ""
        if c.get("id"):
            try:
                d = get(f"contacts/{c['id']}.json", {"fields": "id,primary_email_address"})["data"]
                email = d.get("primary_email_address") or ""
            except requests.HTTPError:
                d = get(f"contacts/{c['id']}.json", {"fields": "id,email_addresses{address}"})["data"]
                email = ", ".join(e["address"] for e in d.get("email_addresses") or [])
        with_email += bool(email)
        print(f"  {c.get('name')}  |  {r.get('description')}  |  email: {email or 'NONE'}")
    print(f"  -> {with_email} of {len(rels)} have an email in Clio")

    print("\n===== EXPENSES (activities type=ExpenseEntry) =====")
    for a in get_all("activities.json", {"matter_id": mid, "type": "ExpenseEntry",
                                         "fields": "id,type,date,price,quantity,total,note,expense_category{name}"}):
        cat = (a.get("expense_category") or {}).get("name")
        print(f"  {a.get('date')}  price={a.get('price')} qty={a.get('quantity')} total={a.get('total')}  "
              f"category={cat}  {(a.get('note') or '')[:60]}")

    print("\n===== DOCUMENTS =====")
    for d in get_all("documents.json", {"matter_id": mid,
                                        "fields": "id,name,created_at,parent{name}"}):
        print(f"  {(d.get('parent') or {}).get('name')}  /  {d.get('name')}  ({d.get('created_at')})")


def main():
    load_env()
    if not os.environ.get("CLIO_ACCESS_TOKEN"):
        sys.exit(f"CLIO_ACCESS_TOKEN is empty in {ENV_FILE}. Paste the access_token from step 6 there.")

    # ---------- STEP 7: who am I + find the matter ----------
    me = get("users/who_am_i.json", {"fields": "id,name,email"})["data"]
    print(f"[ok] Connected to Clio as: {me.get('name')} (user id {me.get('id')})")

    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    search = args[0] if args else "Sapini"
    matters = get(
        "matters.json",
        {
            "query": search,
            "fields": "id,display_number,description,status,open_date,"
                      "statute_of_limitations,practice_area{name},matter_stage{name}",
        },
    )["data"]
    if not matters:
        sys.exit(f"No matter found for '{search}'. Check the matter exists in Clio.")
    m = matters[0]
    mid = m["id"]
    print(f"[ok] Matter found: id={mid} | {m.get('display_number')} | {m.get('description')}")
    print(f"     status={m.get('status')} | stage={(m.get('matter_stage') or {}).get('name')} "
          f"| practice area={(m.get('practice_area') or {}).get('name')}")

    # ---------- STEP 8: count everything ----------
    got = {}

    detail = get(f"matters/{mid}.json",
                 {"fields": "id,custom_field_values{id,value,field_name}"})["data"]
    cfv = [c for c in detail.get("custom_field_values", []) if c.get("value") not in (None, "")]
    got["custom fields filled"] = len(cfv)

    rel = get_all("relationships.json", {"matter_id": mid, "fields": "id,description"})
    got["related contacts (+ client)"] = len(rel) + 1  # +1 = the client

    got["notes"] = len(get_all("notes.json", {"type": "Matter", "matter_id": mid, "fields": "id"}))
    got["communications"] = len(get_all("communications.json", {"matter_id": mid, "fields": "id"}))
    got["tasks"] = len(get_all("tasks.json", {"matter_id": mid, "fields": "id"}))
    got["calendar entries"] = len(get_all("calendar_entries.json", {"matter_id": mid, "fields": "id"}))
    got["expenses"] = len(get_all("activities.json",
                                  {"matter_id": mid, "type": "ExpenseEntry", "fields": "id"}))
    got["documents"] = len(get_all("documents.json", {"matter_id": mid, "fields": "id,name"}))

    print("\n  What                          Expected   Got   OK?")
    all_ok = True
    for k, exp in EXPECTED.items():
        ok = got.get(k) == exp
        all_ok &= ok
        print(f"  {k:<30}{exp:>8}{got.get(k, '-'):>6}   {'yes' if ok else 'NO'}")

    print("\n[ok] All counts match. Clio setup is done." if all_ok
          else "\n[!] Some counts differ. Re-check those parts of the matter in Clio "
               "(see 'Sapini - manual setup guide.pdf').")
    if "--details" in sys.argv:
        show_details(mid)
    print(f"\nSave this for your app: SAPINI search works, matter id = {mid} (look it up by search, don't hardcode).")


if __name__ == "__main__":
    main()
