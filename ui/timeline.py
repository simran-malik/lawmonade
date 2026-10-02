"""Tab 2: Everything, by date. Every note, email, call, task, calendar entry, expense and document in one list.
Each entry shows where it came from. Long text opens in place ("Read all").
Tasks and calendar entries can go on Google Calendar: all at once (under the search bar) or one by one.
On top: "Overdue" (open tasks past due) and "Due today or tomorrow" (open tasks + calendar entries), each with
Email and Text (Twilio) to the task's responsible person in Clio. Then everything else, month by month."""
from datetime import datetime

import streamlit as st

from app import deadlines, gcal, store
from app.config import settings
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


def _entry(it: dict, matter_url: str, flag: str = "") -> str:
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
    late = flag or late
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


def _who() -> str:
    return (st.session_state.get("who") or "").strip()


def _add_one(s: dict, it: dict):
    """Button callback: runs before the page redraws, so the row shows "On your calendar" straight away."""
    try:
        r = gcal.add(s, it, _who())
        st.session_state.gcal_msg = ("ok", "Already on your calendar." if r["status"] == "already"
                                     else f"Added to your calendar: {it.get('title') or '(no title)'}")
    except gcal.CalendarError as e:
        st.session_state.gcal_msg = ("err", f"{e.message} {e.fix}")


def _calendar_bar(s: dict, done: dict):
    """Under the search bar: add every upcoming task and calendar entry that isn't on the calendar yet."""
    if not gcal.ready():
        st.markdown('<span class="lm-pill check">SETUP NEEDED</span> To add tasks and events to Google Calendar, '
                    'run <code>bash run.sh gcal</code> once.', unsafe_allow_html=True)
        return
    todo = gcal.pending(s, done)
    c1, c2 = st.columns([1.6, 3])
    with c1:
        go = st.button(f"Add all to calendar ({len(todo)})" if todo else "All on calendar ✓", key="gcal_all",
                       type="primary", disabled=not todo, use_container_width=True,
                       help="Upcoming tasks and calendar entries that aren't on your Google Calendar yet")
    with c2:
        n_t = sum(1 for it in todo if gcal.kind(it) == "Task")
        n_e = len(todo) - n_t
        st.caption(f"{n_t} open task{'s' * (n_t != 1)} and {n_e} calendar entr{'ies' if n_e != 1 else 'y'} "
                   f"from today on aren't on your calendar yet. "
                   f"{len(done)} already added. Past or finished items can be added one by one below."
                   if todo else f"Everything coming up is on your calendar ({len(done)} added). "
                                "Past or finished items can be added one by one below.")
    if go:
        bar = st.progress(0.0, text="Adding to Google Calendar…")
        try:
            r = gcal.add_many(s, todo, _who(), on_step=lambda i, n, it: bar.progress(
                i / n, text=f"Adding {i + 1} of {n}: {it.get('title') or '(no title)'}"))
        except gcal.CalendarError as e:
            st.session_state.gcal_msg = ("err", f"{e.message} {e.fix}")
        else:
            msg = f"Added {r['added']} to your calendar." + (f" {r['already']} were already there." if r["already"] else "")
            if r["failed"]:
                f = r["failed"][0]
                msg += f" {len(r['failed'])} couldn't be added (first: {f['title']}: {f['error']} {f['fix']})"
            st.session_state.gcal_msg = ("err" if r["failed"] else "ok", msg)
        st.rerun()


def _calendar_cell(s: dict, it: dict, done: dict):
    row = done.get(gcal.key(it))
    if row:
        link = row.get("event_link")
        text = f'<a href="{esc(link)}" target="_blank">On calendar ↗</a>' if link else "On calendar"
        st.markdown(f'<div class="lm-oncal">✓ {text}</div>', unsafe_allow_html=True)
    else:
        st.button("Add to calendar", key=f"gcal_{gcal.key(it)}", on_click=_add_one, args=(s, it),
                  disabled=not gcal.ready(), use_container_width=True,
                  help="Put this on Google Calendar" if gcal.ready() else "Run bash run.sh gcal once first")


# ---------- Overdue / due soon: email or text the responsible person ----------
def _flag(days: int) -> str:
    if days < 0:
        return f'<span class="lm-late">OVERDUE · {-days} day{"s" if days != -1 else ""}</span>'
    return f'<span class="lm-soon">{"DUE TODAY" if days == 0 else "DUE TOMORROW" if days == 1 else f"DUE IN {days} DAYS"}</span>'


def _send_email(s: dict, it: dict, k: str):
    from app import emailer
    ss, to = st.session_state, (st.session_state.get(k + "to") or "").strip()
    try:
        r = emailer.send(to, ss.get(k + "subj") or "Follow-up", ss.get(k + "msg") or "")
        store.log("reminder_email_sent", f"{s['matter']['id']}:{gcal.key(it)}", {"to": r["intended"], "via": r["via"]},
                  actor=_who())
        ss[k + "done"] = ("ok", f"Email sent to {r['to']}.")
    except emailer.EmailError as e:
        store.log("reminder_email_failed", f"{s['matter']['id']}:{gcal.key(it)}", {"to": to, "error": e.message}, actor=_who())
        ss[k + "done"] = ("err", f"{e.message} {e.fix}")


def _send_text(s: dict, it: dict, k: str):
    from app.integrations.sms import send_sms
    ss = st.session_state
    to = deadlines.phone(ss.get(k + "ph"))
    if not to:
        ss[k + "done"] = ("err", "That isn't a phone number we can text. Use 10 digits, or +country code.")
        return
    r = send_sms(to, ss.get(k + "sms") or "")
    ok = bool(r.get("sid")) and r.get("status") not in ("failed", "not_sent")
    store.log("reminder_text_sent" if ok else "reminder_text_failed", f"{s['matter']['id']}:{gcal.key(it)}",
              {"to": "..." + to[-4:], "status": r.get("status"), "reason": r.get("reason", "")}, actor=_who())
    if ok:
        extra = f" (trial account: Twilio sent its {r['sent_template']} template)" if r.get("sent_template") else ""
        ss[k + "done"] = ("ok", f"Text sent to ...{to[-4:]}{extra}.")
    else:
        ss[k + "done"] = ("err", f"Not sent: {r.get('reason') or r.get('status')}")


def _reach_cell(s: dict, it: dict, done: dict):
    """Right-hand column of an overdue / due-soon row: calendar, then Email and Text the responsible person."""
    _calendar_cell(s, it, done)
    who = deadlines.responsible(it, s, it["days"])
    k = f"reach_{gcal.key(it)}_"
    if not who:
        st.caption("No one is assigned in Clio and the case has no responsible attorney.")
        return
    st.caption(f"{who['name']} · {who['role']}")
    with st.popover("Email", use_container_width=True):
        st.text_input("To", value=who["email"], key=k + "to", placeholder="name@firm.com",
                      help="From the task's assignee in Clio" if who["email"] else "Clio has no email for this person: type one")
        st.text_input("Subject", value=who["subject"], key=k + "subj")
        st.text_area("Message (you can edit it)", value=who["draft"], key=k + "msg", height=140)
        st.button("Send email", key=k + "send_email", type="primary", on_click=_send_email, args=(s, it, k),
                  use_container_width=True)
    with st.popover("Text", use_container_width=True):
        st.text_input("Phone", value=who["phone"], key=k + "ph", placeholder="(619) 555-0123",
                      help="From Clio" if who["phone"] else "Clio has no phone for this person: type one")
        st.text_area("Message (you can edit it)", value=who["draft"], key=k + "sms", height=120, max_chars=640)
        twilio = bool(settings.twilio_account_sid and settings.twilio_auth_token and settings.twilio_from_number)
        st.button("Send text (Twilio)", key=k + "send_text", type="primary", on_click=_send_text, args=(s, it, k),
                  disabled=not twilio, use_container_width=True,
                  help=None if twilio else "Add TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN and TWILIO_FROM_NUMBER to .env")
    msg = st.session_state.get(k + "done")
    if msg:
        (st.success if msg[0] == "ok" else st.error)(msg[1])


def _urgent_section(s: dict, title: str, cls: str, items: list[dict], done: dict, url: str):
    st.markdown(f'<div class="lm-month {cls}">{title} ({len(items)})</div>', unsafe_allow_html=True)
    for it in items:
        left, right = st.columns([6, 1.6], vertical_alignment="top")
        with left:
            st.markdown(_entry(it, url, _flag(it["days"])), unsafe_allow_html=True)
        with right:
            _reach_cell(s, it, done)


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

    done = gcal.added(s["matter"]["id"])
    _calendar_bar(s, done)
    msg = st.session_state.pop("gcal_msg", None)
    if msg:
        (st.success if msg[0] == "ok" else st.error)(msg[1])

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

    url = s["matter"].get("url", "")
    late, soon, rest = deadlines.split_urgent(items)
    if late:
        _urgent_section(s, "Overdue", "late", late, done, url)
    if soon:
        n = settings.digest_urgent_days
        _urgent_section(s, "Due today or tomorrow" if n == 1 else f"Due in the next {n} days", "soon", soon, done, url)
    if (late or soon) and rest:
        st.markdown("#### Everything else, by month")

    # Plain entries are drawn together in one block (fast); a task or calendar entry gets its own row with a button
    html, month = [], None
    for it in rest:
        d = _when(it)
        label = d.strftime("%B %Y") if d != datetime.min else "No date"
        if label != month:
            html.append(f'<div class="lm-month">{label}</div>')
            month = label
        if not gcal.can_add(it):
            html.append(_entry(it, url))
            continue
        if html:
            st.markdown("".join(html), unsafe_allow_html=True)
            html = []
        left, right = st.columns([6, 1.3], vertical_alignment="center")
        with left:
            st.markdown(_entry(it, url), unsafe_allow_html=True)
        with right:
            _calendar_cell(s, it, done)
    if html:
        st.markdown("".join(html), unsafe_allow_html=True)
