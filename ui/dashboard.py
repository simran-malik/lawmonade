"""Law-monade dashboard. Run: bash run.sh ui  ->  http://localhost:8501

Flow (3 clicks or less): Open the case -> read the brief -> (later) share with a provider.
"""
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st  # noqa: E402

from app import log, snapshot  # noqa: E402
from app.config import settings  # noqa: E402
from ui import theme  # noqa: E402
from ui.theme import esc  # noqa: E402

log.setup()
theme.apply()
ss = st.session_state
ss.setdefault("snap", None)
ss.setdefault("error", None)
ss.setdefault("query", settings.clio_matter_query)
ss.setdefault("matter_id", None)    # set when a person picked one of several matching cases
ss.setdefault("choices", None)


# ---------- loading ----------
def open_from_clio(query: str, matter_id=None):
    from app.clio import ClioChoice, ClioError, load_steps
    ss.error, ss.choices = None, None
    log.new_run()                      # every log line of this load shares one run id
    state, steps = load_steps(query, matter_id)
    try:
        theme.run_steps(steps, title=f'Opening "{query}" from Clio')
    except ClioChoice as e:            # several cases match: let the person pick, never guess
        ss.choices = e.choices
        return
    except ClioError as e:
        ss.error = (e.message, e.fix)
        use_saved_copy(query)
        return
    except Exception as e:  # unexpected: still say what to do
        log.get("ui").exception("[clio.load] unexpected error")
        ss.error = ("Something went wrong while reading the case.", f"Try again, or use the sample case. Details: {e}")
        use_saved_copy(query)
        return
    snapshot.save(state["snapshot"])
    ss.snap = state["snapshot"]
    ss.matter_id = state["snapshot"]["matter"]["id"]


def use_saved_copy(query: str):
    """Clio failed: if nothing is open yet, show the last copy saved from Clio and say how old it is."""
    if ss.snap is not None:
        return
    saved = snapshot.find_saved(query)
    if saved:
        ss.snap = saved
        msg, fix = ss.error
        ss.error = (f"{msg} You're seeing the copy saved {ago(saved.get('fetched_at')) or 'earlier'}.", fix)


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
                      "Law-monade reads the whole case file in Clio and shows what matters: what it's worth, "
                      "what's overdue, and what changed. Nothing in Clio is ever changed.")
    if ss.error:
        theme.error_box(*ss.error)
    _, mid, _ = st.columns([1, 2, 1])
    with mid:
        query = st.text_input("Case or client name", value=settings.clio_matter_query,
                              placeholder="e.g. Sapini", label_visibility="collapsed")
        if st.button("Open case from Clio", type="primary", use_container_width=True):
            ss.query, ss.matter_id = query.strip() or settings.clio_matter_query, None
            open_from_clio(ss.query)
            st.rerun()
        if ss.choices:
            pick_case(ss.choices)
        if st.button("Try the sample case", use_container_width=True,
                     help="Uses the organizers' sample file. Marked as Demo mode."):
            open_sample()
            st.rerun()


def pick_case(choices: list[dict]):
    """Several Clio cases match the search: show them and open only the one a person picks."""
    st.markdown(f"**{len(choices)} cases match \"{esc(ss.query)}\". Which one?**")
    for c in choices:
        label = " · ".join(x for x in (c["client"], c["number"], c["description"], c["status"]) if x)
        if st.button(label, key=f"pick_{c['id']}", use_container_width=True):
            ss.matter_id = c["id"]
            open_from_clio(ss.query, c["id"])
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


def money_row(s: dict):
    from app import brief
    mid = s["matter"]["id"]
    # Same brief as the API; drawing it never writes to the DB (only the buttons below do)
    ks = brief.build(s, lien_breakdown(s))["cards"]

    h, who = st.columns([3, 1])
    with h:
        st.markdown("### What it's worth, and what's behind it")
    with who:
        st.text_input("Reviewing as", key="who", placeholder="Your name", help="Saved with each approval or fix")
    st.markdown(theme.review_summary(ks), unsafe_allow_html=True)
    for col, k in zip(st.columns(len(ks)), ks):
        with col:
            st.markdown(theme.card(k), unsafe_allow_html=True)
            needs = k["review"]["status"] == "needs_review"
            with st.expander("Where this comes from" + (" · review" if needs else "")):
                st.markdown(theme.source_html(k), unsafe_allow_html=True)
                for it in k.get("items") or []:
                    st.markdown(f"- {it['text']}" + (f" · [Open in Clio ↗]({it['url']})" if it.get("url") else ""))
                review_buttons(mid, k)


def review_buttons(mid, k: dict):
    """Looks good / Something wrong? (and undo). Saved in Law-monade's own database; Clio is never changed."""
    from app import store
    key, status = k["key"], k["review"]["status"]
    who = ss.get("who", "").strip()
    seen = (ss.snap or {}).get("fetched_at", "")     # which copy of the case the person looked at
    if status == "needs_review" and not k.get("edited"):
        a, b = st.columns(2)
        if a.button("✓ Looks good", key=f"ok_{key}", type="primary", use_container_width=True):
            store.set_card_review(mid, key, "approved", k["amount"], who, snapshot=seen)
            st.rerun()
        if b.button("Something wrong?", key=f"bad_{key}", use_container_width=True):
            ss[f"fix_{key}"] = True
    elif status == "approved":
        a, b = st.columns(2)
        if a.button("Undo approval", key=f"unok_{key}", use_container_width=True):
            store.set_card_review(mid, key, "needs_review", k["amount"], who, snapshot=seen)
            st.rerun()
        if b.button("Something wrong?", key=f"bad_{key}", use_container_width=True):
            ss[f"fix_{key}"] = True
    elif k.get("edited"):
        a, b = st.columns(2)
        if a.button("Change the fix", key=f"refix_{key}", use_container_width=True):
            ss[f"fix_{key}"] = True
        if b.button("Undo: use the Clio number", key=f"undo_{key}", use_container_width=True):
            store.clear_card_edit(mid, key, who)
            st.rerun()
    elif st.button("Something wrong?", key=f"bad_{key}", use_container_width=True):
        ss[f"fix_{key}"] = True
    if ss.get(f"fix_{key}"):
        fix_form(mid, k, who)


def fix_form(mid, k: dict, who: str):
    """Correct the number. Clio stays as it is (read-only); the card shows both."""
    key, edited = k["key"], k.get("edited")
    with st.form(f"edit_{key}"):
        st.markdown(f"Clio says **{k.get('clio_value_text', k['value'])}**. Your fix is saved in Law-monade only.")
        value = st.number_input("Correct amount ($)", min_value=0.0, step=100.0, format="%.2f",
                                value=float(k["amount"] or 0))
        note = st.text_input("What's wrong?", value=(edited or {}).get("note", ""),
                             placeholder="e.g. Adjuster confirmed $50,000 on the phone")
        a, b = st.columns(2)
        save = a.form_submit_button("Save fix", type="primary", use_container_width=True)
        cancel = b.form_submit_button("Cancel", use_container_width=True)
    if save or cancel:
        if save:
            from app import store
            store.save_card_edit(mid, key, value, note.strip(), who, k.get("clio_amount", k["amount"]))
        ss[f"fix_{key}"] = False
        st.rerun()


def lien_breakdown(s: dict) -> dict:
    """AI lien breakdown, once per case version (the answer is also cached on disk, so reopening is free)."""
    from app import liens
    key = f"liens_{s['matter']['id']}_{s.get('fetched_at')}"
    if key not in ss:
        with st.spinner("Sorting the lien field (AI, then checked against Clio)…"):
            ss[key] = liens.analyze(s)
    return ss[key]


def case_screen(s: dict):
    theme.top_bar(s["source"])
    case_header(s)
    a, b, _ = st.columns([1, 1, 3])
    with a:
        refresh = s["source"] == "clio" and st.button("Refresh from Clio", use_container_width=True,
                                                      help="Read the latest notes, emails and tasks again")
    with b:
        if st.button("Open another case", use_container_width=True):
            ss.snap, ss.error, ss.matter_id, ss.choices = None, None, None, None
            st.rerun()
    if refresh:   # outside the button column, so the progress box uses the full page width
        _, mid, _ = st.columns([1, 2, 1])
        with mid:
            open_from_clio(ss.query, ss.matter_id)
        st.rerun()
    if ss.error:
        theme.error_box(*ss.error)

    brief, timeline, share = st.tabs(["Case brief", "Everything, by date", "Share with a provider"])
    with brief:
        money_row(s)
        c = snapshot.counts(s)
        st.caption(f"Read from {c['notes']} notes · {c['communications']} emails and calls · {c['tasks']} tasks · "
                   f"{c['calendar']} calendar entries · {c['expenses']} expenses · {c['documents']} documents · "
                   f"{c['contacts']} people and companies")
    with timeline:
        from ui import timeline as tl
        tl.render(s)
    with share:
        from ui import share_tab
        share_tab.render(s)


share_token = st.query_params.get("share")
if share_token:      # providers should use the provider portal (bash run.sh provider); kept here for local testing
    from ui import provider_view
    provider_view.page(share_token)
elif ss.snap:
    case_screen(ss.snap)
else:
    welcome()
