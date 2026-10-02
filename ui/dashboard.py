"""Lawmonade dashboard. Run: bash run.sh ui  ->  http://localhost:8501

Flow (3 clicks or less): Open the case -> read the brief -> (later) share with a provider.
"""
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st  # noqa: E402

from app import snapshot  # noqa: E402
from app.config import settings  # noqa: E402
from ui import theme  # noqa: E402
from ui.theme import esc  # noqa: E402

theme.apply()
ss = st.session_state
ss.setdefault("snap", None)
ss.setdefault("error", None)
ss.setdefault("query", settings.clio_matter_query)


# ---------- loading ----------
def open_from_clio(query: str):
    from app.clio import ClioError, load_steps
    ss.error = None
    state, steps = load_steps(query)
    try:
        theme.run_steps(steps, title=f'Opening "{query}" from Clio')
    except ClioError as e:
        ss.error = (e.message, e.fix)
        return
    except Exception as e:  # unexpected: still say what to do
        ss.error = ("Something went wrong while reading the case.", f"Try again, or use the sample case. Details: {e}")
        return
    snapshot.save(state["snapshot"])
    ss.snap = state["snapshot"]


def open_sample():
    ss.error = None
    holder = {}
    path = Path(settings.demo_file)
    if not path.exists():
        ss.error = ("The sample case file is missing.",
                    f"Put sapini-clio-data.json at {path}, or set DEMO_FILE in .env.")
        return
    theme.run_steps([
        ("Reading the sample case", lambda: holder.update(s=snapshot.from_sample_file(path))),
        ("Putting it together", lambda: snapshot.save(holder["s"])),
    ], title="Opening the sample case")
    ss.snap = holder["s"]


def ago(iso: str) -> str:
    try:
        secs = (datetime.now(timezone.utc) - datetime.fromisoformat(iso)).total_seconds()
    except (TypeError, ValueError):
        return ""
    if secs < 90:
        return "just now"
    if secs < 3600:
        return f"{int(secs // 60)} min ago"
    return f"{int(secs // 3600)} h ago"


# ---------- screens ----------
def welcome():
    theme.top_bar(None)
    theme.empty_state("Get up to speed on any case in two minutes",
                      "Lawmonade reads the whole case file in Clio and shows what matters: what it's worth, "
                      "what's overdue, and what changed. Nothing in Clio is ever changed.")
    if ss.error:
        theme.error_box(*ss.error)
    _, mid, _ = st.columns([1, 2, 1])
    with mid:
        query = st.text_input("Case or client name", value=settings.clio_matter_query,
                              placeholder="e.g. Sapini", label_visibility="collapsed")
        if st.button("Open case from Clio", type="primary", use_container_width=True):
            ss.query = query.strip() or settings.clio_matter_query
            open_from_clio(ss.query)
            st.rerun()
        if st.button("Try the sample case", use_container_width=True,
                     help="Uses the organizers' sample file. Marked as Demo mode."):
            open_sample()
            st.rerun()


def case_header(s: dict):
    m, f = s["matter"], s.get("fields", {})
    chips = [("Stage", m.get("stage")), ("Status", m.get("status")),
             ("Incident", snapshot.nice_date(f.get("Date of Incident"))),
             ("Opened", snapshot.nice_date(m.get("open_date"))),
             ("Statute of limitations", snapshot.nice_date(m.get("sol_date")))]
    chip_html = "".join(f'<span class="lm-chip">{esc(k)}: <b>{esc(v)}</b></span>' for k, v in chips if v)
    where = "Clio" if s["source"] == "clio" else "the sample file"
    st.markdown(f'<div class="lm-case"><h1>{esc(m.get("client") or m.get("description"))}</h1>'
                f'<div class="desc">{esc(m.get("description"))}'
                f'{" · " + esc(m.get("number")) if m.get("number") else ""}</div>'
                f'<div class="lm-chips">{chip_html}'
                f'<span class="lm-chip">Data from {esc(where)}: <b>{esc(ago(s.get("fetched_at")))}</b></span></div></div>',
                unsafe_allow_html=True)


def case_screen(s: dict):
    theme.top_bar(s["source"])
    case_header(s)
    a, b, _ = st.columns([1, 1, 3])
    with a:
        if s["source"] == "clio" and st.button("Refresh from Clio", use_container_width=True,
                                                help="Read the latest notes, emails and tasks again"):
            open_from_clio(ss.query)
            st.rerun()
    with b:
        if st.button("Open another case", use_container_width=True):
            ss.snap, ss.error = None, None
            st.rerun()
    if ss.error:
        theme.error_box(*ss.error)

    brief, timeline, share = st.tabs(["Case brief", "Everything, by date", "Share with a provider"])
    with brief:
        c = snapshot.counts(s)
        st.markdown(f"### What's in this case file")
        st.markdown(f"{c['notes']} notes · {c['communications']} emails and calls · {c['tasks']} tasks · "
                    f"{c['calendar']} calendar entries · {c['expenses']} expenses · {c['documents']} documents · "
                    f"{c['contacts']} people and companies")
        st.info("The two-minute brief (worth, coverage, overdue, what changed) is added in the next steps.")
    with timeline:
        st.info("The full timeline is added in a later step.")
    with share:
        st.info("Sharing with providers is added in a later step.")


if ss.snap:
    case_screen(ss.snap)
else:
    welcome()
