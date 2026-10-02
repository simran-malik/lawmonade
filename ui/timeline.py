"""Tab 2: Everything, by date. Every note, email, call, task, calendar entry, expense and document in one list.
Each entry shows where it came from. Long text opens in place ("Read all")."""
from datetime import datetime

import streamlit as st

from app.share import overdue
from app.snapshot import nice_date
from ui.theme import esc

KINDS = {"Notes": "notes", "Emails and calls": "communications", "Tasks": "tasks", "Calendar": "calendar",
         "Expenses": "expenses", "Documents": "documents"}
PREVIEW = 260   # characters shown before "Read all"


def _items(s: dict, groups: list[str]) -> list[dict]:
    out = []
    for g in groups:
        for it in s.get(KINDS[g], []):
            out.append(it | {"kind": it.get("kind") or it["src"]["kind"]})
    return out


def _when(it) -> datetime:
    try:
        return datetime.fromisoformat(str(it.get("date")).replace("Z", "+00:00")).replace(tzinfo=None)
    except (TypeError, ValueError):
        return datetime.min


def _entry(it: dict, matter_url: str) -> str:
    text = (it.get("text") or "").strip()
    if it.get("kind") == "Document" and it.get("folder"):
        text = f"Folder: {it['folder']}"
    if it.get("kind") == "Expense" and it.get("amount") is not None:
        text = f"${it['amount']:,.2f} · {text}"
    late = ""
    if it.get("kind") == "Task":
        done = (it.get("status") or "").lower() in ("complete", "completed", "done")
        late = '<span class="lm-late">OVERDUE</span>' if (not done and overdue(it.get("date"))) else \
               ('<span class="lm-srcline"> · done</span>' if done else '<span class="lm-srcline"> · open</span>')
    # Long text: show whole sentences first, the rest behind "Read the rest" (never cut mid-sentence, no "…")
    cut = text.rfind(". ", 0, PREVIEW) + 1
    if len(text) <= PREVIEW or cut <= 0:
        body = f'<div class="x">{esc(text)}</div>'
    else:
        body = (f'<div class="x">{esc(text[:cut])}</div>'
                f'<details><summary>Read the rest</summary><div class="x">{esc(text[cut:].strip())}</div></details>')
    url, hint = it["src"].get("url"), it["src"].get("hint")
    if url and hint:
        place = {"Calendar": "Calendar", "Task": "Tasks"}.get(it["kind"], "Activities")
        link = (f' · <a href="{esc(url)}" target="_blank">Open {place} in Clio ↗</a>'
                f' <span class="lm-hint">then search “{esc(hint)}”</span>')
    elif url:
        link = f' · <a href="{esc(url)}" target="_blank">Open in Clio ↗</a>'
    else:
        link = f' · <a href="{esc(matter_url)}" target="_blank">Open case in Clio ↗</a>' if matter_url else ""
    kind_cls = esc(it["kind"].split()[0])
    return (f'<div class="lm-item"><div class="d">{esc(nice_date(it.get("date")) or "No date")}</div><div>'
            f'<div class="h"><span class="lm-kind {kind_cls}">{esc(it["kind"])}</span>{esc(it.get("title") or "(no title)")}{late}</div>'
            f'{body if text else ""}<div class="lm-srcline">Source: {esc(it["src"]["where"])} · {esc(it["src"]["label"])}{link}</div>'
            f'</div></div>')


def render(s: dict):
    st.markdown("### Everything in the file, newest first")
    c1, c2, c3 = st.columns([3, 4, 1.4])
    with c1:
        q = st.text_input("Search", placeholder="Search: e.g. surgery, Capiola, lien", label_visibility="collapsed")
    with c2:
        groups = st.multiselect("Show", list(KINDS), default=list(KINDS), label_visibility="collapsed",
                                placeholder="Pick what to show")
    with c3:
        oldest = st.toggle("Oldest first")

    items = _items(s, groups or list(KINDS))
    total = len(items)
    if q.strip():
        words = q.lower().split()
        items = [it for it in items if all(w in f"{it.get('title', '')} {it.get('text', '')}".lower() for w in words)]
    items.sort(key=_when, reverse=not oldest)

    st.caption(f"Showing {len(items)} of {total} entries")
    if not items:
        st.markdown('<div class="lm-never">Nothing matches. Try fewer words, or turn more types back on.</div>',
                    unsafe_allow_html=True)
        return

    html, month = [], None
    for it in items:
        d = _when(it)
        label = d.strftime("%B %Y") if d != datetime.min else "No date"
        if label != month:
            html.append(f'<div class="lm-month">{label}</div>')
            month = label
        html.append(_entry(it, s["matter"].get("url", "")))
    st.markdown("".join(html), unsafe_allow_html=True)
